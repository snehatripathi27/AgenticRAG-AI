"""One execution path for synchronous CLI runs and background API runs."""

import hashlib
import json
import logging
import math
import platform
import time
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version

from .backends import create_backend
from .metrics import metrics
from .tasks import load_samples, validate_tasks

logger = logging.getLogger(__name__)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def execute(config, registry, store, run_id=None, backend_factory=create_backend):
    validate_tasks(config, registry)
    run_id = run_id or store.create(config)
    started = time.perf_counter()
    store.update(run_id, status="running")
    try:
        versions = {}
        for package in ("benchlab-eval", "transformers", "torch", "vllm", "datasets", "httpx"):
            try:
                versions[package] = version(package)
            except PackageNotFoundError:
                pass
        manifest = {
            "config_sha256": digest(config.model_dump()),
            "python": platform.python_version(),
            "packages": versions,
            "tasks": {},
            "protocol": "generated-answer-v1",
            "seed": config.seed,
        }
        prepared = {}
        for task_id in config.tasks:
            task = registry[task_id]
            samples = load_samples(task, config.limit, config.seed, config.dataset_revisions.get(task_id))
            if not samples:
                raise ValueError(f"Task {task_id} has no samples")
            prepared[task_id] = samples
            manifest["tasks"][task_id] = {
                "source": task.source,
                "subset": task.subset,
                "split": task.split,
                "revision": config.dataset_revisions.get(task_id, "main"),
                "samples_sha256": digest([asdict(s) for s in samples]),
                "prompt_sha256": digest(config.prompts.get(task_id, task.prompt)),
                "metric": task.metric,
            }
        store.update(run_id, total=sum(len(s) for s in prepared.values()), manifest=manifest)
        backend = backend_factory(config.model, config.seed)
        scorers = metrics()
        results = {}
        for task_id, samples in prepared.items():
            task = registry[task_id]
            scores = []
            for start in range(0, len(samples), config.batch_size):
                batch = samples[start : start + config.batch_size]
                prompts = [
                    config.prompts.get(task_id, task.prompt)
                    .format(question=s.question, choices=s.choices, context=s.context)
                    .strip()
                    for s in batch
                ]
                batch_started = time.perf_counter()
                predictions = backend.generate(prompts)
                latency = (time.perf_counter() - batch_started) / len(batch)
                if len(predictions) != len(batch) or any(not isinstance(p, str) for p in predictions):
                    raise ValueError("Backend must return one string for each prompt")
                logs = []
                for sample, prompt, prediction in zip(batch, prompts, predictions):
                    score = float(scorers[task.metric](prediction, sample.reference))
                    if not math.isfinite(score) or not 0 <= score <= 1:
                        raise ValueError("Metrics must return a finite score between 0 and 1")
                    scores.append(score)
                    logs.append(
                        {
                            "task": task_id,
                            "sample_id": sample.id,
                            "prompt": prompt,
                            "reference": sample.reference,
                            "prediction": prediction,
                            "score": score,
                            "metric": task.metric,
                            "latency_seconds": latency,
                        }
                    )
                store.add_samples(run_id, logs)
            results[task_id] = {
                "score": sum(scores) / len(scores),
                "count": len(scores),
                "metric": task.metric,
            }
            store.update(run_id, results=results)
        store.update(run_id, status="completed", duration=time.perf_counter() - started)
    except Exception as exc:  # noqa: BLE001 - persist every inference failure
        # Provider exceptions can contain credentials/URLs. Keep persisted errors bounded.
        message = (
            str(exc)
            if isinstance(exc, (ValueError, RuntimeError))
            else f"{type(exc).__name__}: evaluation failed; verify model, dataset access, and optional dependencies"
        )
        import os

        secret = os.environ.get(config.model.api_key_env)
        if secret:
            message = message.replace(secret, "[redacted]")
        store.update(run_id, status="failed", error=message[:1000], duration=time.perf_counter() - started)
        logger.error("Run %s failed: %s", run_id, message[:1000])
    return store.get(run_id)
