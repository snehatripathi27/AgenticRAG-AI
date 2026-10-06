"""Local, single-worker evaluation API; bind to loopback unless behind authentication."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse

from .config import RunConfig
from .runner import execute
from .storage import Store
from .tasks import catalog, validate_tasks


def create_app(db_path=".benchlab/runs.db", task_dir: Path | None = None):
    store = Store(db_path)
    registry = catalog(task_dir)

    @asynccontextmanager
    async def lifespan(app):
        store.interrupt_pending()
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="benchlab") as executor:
            app.state.executor = executor
            yield

    app = FastAPI(
        title="BenchLab",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    def validate(config):
        try:
            validate_tasks(config, registry)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/tasks")
    def tasks():
        return [task.public() for task in registry.values()]

    @app.post("/api/configs/validate")
    def validate_config(config: RunConfig):
        validate(config)
        return {"valid": True, "config": config.model_dump()}

    @app.get("/api/configs")
    def configs():
        return store.configs()

    @app.post("/api/configs", status_code=201)
    def save_config(config: RunConfig):
        validate(config)
        return {"id": store.save_config(config)}

    @app.post("/api/configs/yaml", response_class=PlainTextResponse)
    def config_yaml(config: RunConfig):
        validate(config)
        return yaml.safe_dump(config.model_dump(), sort_keys=False)

    @app.get("/api/runs")
    def runs():
        return store.runs()

    @app.post("/api/runs", status_code=202)
    def launch(config: RunConfig):
        validate(config)
        run_id = store.create(config)
        app.state.executor.submit(execute, config, registry, store, run_id)
        return {"id": run_id, "status": "queued"}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        run = store.get(run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return run

    @app.get("/api/runs/{run_id}/samples")
    def samples(run_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        get_run(run_id)
        return store.samples(run_id, limit, offset)

    return app
