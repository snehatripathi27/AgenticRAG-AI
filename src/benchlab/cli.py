"""Command line interface. Use --help on a command for examples/options."""

import argparse
import json
import logging
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from .config import RunConfig, load_config
from .runner import execute
from .storage import Store
from .tasks import catalog, validate_tasks


def parser():
    root = argparse.ArgumentParser(prog="benchlab", description="Repeatable language model evaluations")
    root.add_argument("--db", type=Path, default=Path(".benchlab/runs.db"), help="SQLite results database")
    root.add_argument("--task-dir", type=Path, help="Directory of trusted custom task YAML files")
    sub = root.add_subparsers(dest="command", required=True)
    tasks = sub.add_parser("tasks", help="List available tasks")
    tasks.add_argument("--json", action="store_true")
    validate = sub.add_parser("validate", help="Validate a YAML or JSON config without loading a model")
    validate.add_argument("config", type=Path)
    run = sub.add_parser("run", help="Run an evaluation")
    run.add_argument("--config", type=Path)
    run.add_argument("--model")
    run.add_argument("--backend", choices=["demo", "hf", "vllm", "api"])
    run.add_argument("--tasks", nargs="+", help="Task IDs separated by spaces")
    run.add_argument("--name")
    run.add_argument("--limit", type=int)
    run.add_argument("--seed", type=int)
    run.add_argument("--batch-size", type=int)
    run.add_argument("--base-url")
    run.add_argument("--output", type=Path, help="Write full result JSON including all sample logs")
    result = sub.add_parser("results", help="List runs or inspect/export a run")
    result.add_argument("run_id", nargs="?")
    result.add_argument("--format", choices=["table", "json", "jsonl"], default="table")
    serve = sub.add_parser("serve", help="Start the local API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8001)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    console = Console()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        registry = catalog(args.task_dir)
        if args.command == "tasks":
            if args.json:
                print(json.dumps([t.public() for t in registry.values()], indent=2))
            else:
                table = Table("Task", "Category", "Metric", "Source")
                for task in registry.values():
                    table.add_row(task.id, task.category, task.metric, task.source)
                console.print(table)
            return 0
        if args.command == "validate":
            config = load_config(args.config)
            validate_tasks(config, registry)
            console.print(
                f"[green]Valid[/green]: {config.name} · {len(config.tasks)} tasks · {config.model.backend}/{config.model.name}"
            )
            return 0
        if args.command == "serve":
            import uvicorn

            from .api import create_app

            uvicorn.run(create_app(args.db, args.task_dir), host=args.host, port=args.port)
            return 0
        store = Store(args.db)
        if args.command == "run":
            data = (load_config(args.config) if args.config else RunConfig()).model_dump()
            for name in ("tasks", "name", "limit", "seed", "batch_size"):
                if getattr(args, name) is not None:
                    data[name] = getattr(args, name)
            for flag, name in (("model", "name"), ("backend", "backend"), ("base_url", "base_url")):
                if getattr(args, flag) is not None:
                    data["model"][name] = getattr(args, flag)
            config = RunConfig.model_validate(data)
            run = execute(config, registry, store)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps({**run, "samples": store.samples(run["id"], limit=-1)}, indent=2)
                )
            console.print(
                f"Run {run['id']} · {run['status']} · {run['completed']}/{run['total']} samples · {run['duration']:.2f}s"
            )
            table = Table("Task", "Metric", "Score", "Samples")
            for name, result in run["results"].items():
                table.add_row(name, result["metric"], f"{result['score']:.2%}", str(result["count"]))
            console.print(table)
            if run["error"]:
                console.print(run["error"], markup=False)
            return 0 if run["status"] == "completed" else 1
        runs = [store.get(args.run_id)] if args.run_id else store.runs()
        if args.run_id and runs[0] is None:
            raise ValueError("Run not found")
        if args.format == "jsonl":
            if not args.run_id:
                raise ValueError("jsonl requires a run ID")
            for sample in store.samples(args.run_id, limit=-1):
                print(json.dumps(sample))
        elif args.format == "json":
            print(
                json.dumps(
                    {**runs[0], "samples": store.samples(args.run_id, limit=-1)} if args.run_id else runs,
                    indent=2,
                )
            )
        else:
            table = Table("Run", "Name", "Model", "Status", "Samples")
            for run in runs:
                table.add_row(
                    run["id"],
                    run["name"],
                    run["config"]["model"]["name"],
                    run["status"],
                    str(run["completed"]),
                )
            console.print(table)
        return 0
    except (ValueError, OSError, RuntimeError, yaml.YAMLError) as exc:
        Console(stderr=True).print(str(exc), markup=False)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
