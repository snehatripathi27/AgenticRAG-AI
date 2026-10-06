import json
import subprocess
import sys
import time

from fastapi.testclient import TestClient

from benchlab.api import create_app
from benchlab.config import RunConfig
from benchlab.storage import Store


def test_api_end_to_end(tmp_path):
    db = tmp_path / "runs.db"
    with TestClient(create_app(db)) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert len(client.get("/api/tasks").json()) == 8
        assert client.get("/api/docs").status_code == 200
        assert client.get("/api/openapi.json").status_code == 200
        config = RunConfig(limit=3).model_dump()
        assert client.post("/api/configs/validate", json=config).json()["valid"]
        assert client.post("/api/configs", json=config).status_code == 201
        assert client.get("/api/configs").json()[0]["config"] == config
        assert "seed: 42" in client.post("/api/configs/yaml", json=config).text
        response = client.post("/api/runs", json=config)
        assert response.status_code == 202
        id_ = response.json()["id"]
        for _ in range(100):
            run = client.get(f"/api/runs/{id_}").json()
            if run["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        assert run["status"] == "completed"
        assert run["completed"] == 9
        a = client.get(f"/api/runs/{id_}/samples?limit=2").json()
        b = client.get(f"/api/runs/{id_}/samples?limit=2&offset=2").json()
        assert len(a) == len(b) == 2 and a != b
        assert client.get(f"/api/runs/{id_}/samples?limit=0").status_code == 422
        assert client.get("/api/runs/missing").status_code == 404
        assert client.get("/api/runs/missing/samples").status_code == 404
        assert client.post("/api/runs", json={**config, "tasks": ["missing"]}).status_code == 422
        assert client.post("/api/configs", json={**config, "limit": 0}).status_code == 422
    with TestClient(create_app(db)) as client:
        assert client.get("/api/runs").json()[0]["status"] == "completed"
        assert len(client.get("/api/configs").json()) == 1


def test_restart_marks_incomplete_runs(tmp_path):
    store = Store(tmp_path / "runs.db")
    id_ = store.create(RunConfig())
    with TestClient(create_app(store.path)) as client:
        assert client.get(f"/api/runs/{id_}").json()["status"] == "interrupted"


def test_cli_workflow_and_exit_codes(tmp_path):
    def cli(*args):
        return subprocess.run(
            [sys.executable, "-m", "benchlab.cli", "--db", str(tmp_path / "cli.db"), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    tasks = cli("tasks", "--json")
    assert tasks.returncode == 0 and len(json.loads(tasks.stdout)) == 8
    assert cli("validate", "examples/demo.yaml").returncode == 0
    output = tmp_path / "result.json"
    run = cli("run", "--config", "examples/demo.yaml", "--limit", "3", "--output", str(output))
    assert run.returncode == 0, run.stderr
    result = json.loads(output.read_text())
    assert len(result["samples"]) == 9
    exported = cli("results", result["id"], "--format", "jsonl")
    assert len(exported.stdout.splitlines()) == 9
    assert all("prediction" in json.loads(line) for line in exported.stdout.splitlines())
    assert cli("run", "--tasks", "unknown").returncode == 2
    assert cli("run", "--limit", "0").returncode == 2
    assert cli("results", "missing").returncode == 2
    assert cli("run", "--backend", "api", "--tasks", "demo_math").returncode == 1


def test_cli_invalid_yaml_is_concise(tmp_path):
    config = tmp_path / "broken.yaml"
    config.write_text("tasks: [unclosed")
    result = subprocess.run(
        [sys.executable, "-m", "benchlab.cli", "validate", str(config)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
