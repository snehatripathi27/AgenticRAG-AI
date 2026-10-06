import json

import pytest
from pydantic import ValidationError

from benchlab.config import ModelConfig, RunConfig, load_config
from benchlab.metrics import choice_accuracy, exact_match, numeric_match, token_f1
from benchlab.runner import execute
from benchlab.storage import Store
from benchlab.tasks import catalog, check_prompt, validate_tasks


@pytest.mark.parametrize(
    "prediction,reference,expected",
    [
        ("B. explanation", "B", 1),
        ("Answer: (A)", "A", 1),
        ("Because it is A", "B", 0),
        ("The answer is B", "B", 0),
        ("", "A", 0),
    ],
)
def test_choice_extraction(prediction, reference, expected):
    assert choice_accuracy(prediction, reference) == expected


def test_metrics():
    assert exact_match("  PARIS! ", "Paris") == 1
    assert exact_match("Paris is nice", "Paris") == 0
    assert numeric_match("Work: 2 * 600. Final: 1,200", "1200") == 1
    assert numeric_match("No answer", "0") == 0
    assert numeric_match("0.5", ".5") == 1
    assert numeric_match("1e3", "1000") == 1
    assert token_f1("a a b", "a b b") == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": 0},
        {"tasks": []},
        {"seed": -1},
        {"tasks": ["demo_math", "demo_math"]},
        {"surprise": True},
        {"model": {"api_key": "do-not-store"}},
        {"prompts": {"other": "x"}},
    ],
)
def test_invalid_config(payload):
    with pytest.raises(ValidationError):
        RunConfig.model_validate(payload)


@pytest.mark.parametrize(
    "url", ["ftp://host", "http://user:pass@host", "https://host?key=foo", "https://host/#secret"]
)
def test_reject_secret_urls(url):
    with pytest.raises(ValidationError):
        ModelConfig(base_url=url)


@pytest.mark.parametrize(
    "prompt", ["{reference}", "{question.__class__}", "{question!r}", "{question:>10}", "bad {"]
)
def test_unsafe_or_invalid_prompt(prompt):
    with pytest.raises(ValueError):
        check_prompt(prompt)


def test_config_file_and_task_validation(tmp_path):
    path = tmp_path / "run.yaml"
    path.write_text("name: repeatable\nlimit: 3\ntasks: [demo_math]\n")
    assert load_config(path).limit == 3
    # The sample cap must allow the largest built-in benchmark to run in full.
    assert RunConfig(limit=max(t.size for t in catalog().values())).limit == 10042
    with pytest.raises(ValueError, match="Unknown tasks"):
        validate_tasks(RunConfig(tasks=["missing"]), catalog())
    with pytest.raises(ValueError, match="demo backend"):
        validate_tasks(RunConfig(tasks=["gsm8k"]), catalog())


def test_repeatability_and_manifest(tmp_path):
    store = Store(tmp_path / "runs.db")
    config = RunConfig(limit=6)
    a = execute(config, catalog(), store)
    b = execute(config, catalog(), store)
    assert a["status"] == b["status"] == "completed"
    assert a["results"] == b["results"]
    assert a["manifest"] == b["manifest"]
    assert a["completed"] == 18
    assert a["results"]["demo_math"]["score"] == 1
    assert a["results"]["demo_math"]["count"] == 6
    clean = lambda rows: [{k: v for k, v in row.items() if k != "latency_seconds"} for row in rows]
    assert clean(store.samples(a["id"])) == clean(store.samples(b["id"]))
    c = execute(config.model_copy(update={"seed": 99}), catalog(), store)
    assert (
        c["manifest"]["tasks"]["demo_math"]["samples_sha256"]
        != a["manifest"]["tasks"]["demo_math"]["samples_sha256"]
    )
    assert Store(tmp_path / "runs.db").get(a["id"]) == a


def test_model_cannot_see_reference_and_partial_failure_is_saved(tmp_path):
    calls = []

    class BrokenBackend:
        def generate(self, prompts):
            calls.append(prompts)
            if len(calls) == 2:
                raise RuntimeError("provider unavailable")
            return ["5"] * len(prompts)

    store = Store(tmp_path / "runs.db")
    run = execute(
        RunConfig(tasks=["demo_math"], batch_size=2, limit=4),
        catalog(),
        store,
        backend_factory=lambda *_: BrokenBackend(),
    )
    assert all(isinstance(p, str) for p in calls[0])
    assert run["status"] == "failed"
    assert run["completed"] == 2
    assert len(store.samples(run["id"])) == 2
    assert run["error"] == "provider unavailable"
    assert run["duration"] > 0


def test_wrong_output_count_fails(tmp_path):
    class Wrong:
        def generate(self, prompts):
            return []

    run = execute(RunConfig(), catalog(), Store(tmp_path / "runs.db"), backend_factory=lambda *_: Wrong())
    assert run["status"] == "failed"
    assert "one string" in run["error"]


def test_custom_task_execution(tmp_path):
    (tmp_path / "test.yaml").write_text(
        'id: custom\ntitle: Custom\nmetric: token_f1\nprompt: "{question}"\ndata_file: samples.jsonl\n'
    )
    (tmp_path / "samples.jsonl").write_text(
        json.dumps({"id": "one", "question": "Say hello", "reference": "hello world"})
    )
    registry = catalog(tmp_path)
    assert registry["custom"].size == 1

    class Backend:
        def generate(self, prompts):
            assert prompts == ["Say hello"]
            return ["hello"]

    run = execute(
        RunConfig(model=ModelConfig(backend="api"), tasks=["custom"]),
        registry,
        Store(tmp_path / "runs.db"),
        backend_factory=lambda *_: Backend(),
    )
    assert run["status"] == "completed"
    assert run["results"]["custom"]["score"] == pytest.approx(2 / 3)


def test_custom_file_escape(tmp_path):
    (tmp_path / "test.yaml").write_text("id: custom\ntitle: Custom\ndata_file: ../private.jsonl\n")
    with pytest.raises(ValueError, match="inside task directory"):
        catalog(tmp_path)


def test_secrets_are_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-secret")

    def failed(*_):
        raise RuntimeError("credential local-test-secret rejected")

    run = execute(RunConfig(), catalog(), Store(tmp_path / "runs.db"), backend_factory=failed)
    assert "local-test-secret" not in json.dumps(run)
    assert "[redacted]" in run["error"]


def test_metric_plugin_registration_and_duplicate(monkeypatch):
    from types import SimpleNamespace

    from benchlab.metrics import metrics

    plugin = SimpleNamespace(name="custom_score", load=lambda: lambda p, r: 0.75)
    monkeypatch.setattr("benchlab.metrics.entry_points", lambda **_: [plugin])
    assert metrics()["custom_score"]("prediction", "reference") == 0.75
    plugin.name = "exact_match"
    with pytest.raises(ValueError, match="Duplicate metric"):
        metrics()


def test_nonfinite_plugin_score_fails(tmp_path, monkeypatch):
    from benchlab import runner

    monkeypatch.setattr(runner, "metrics", lambda: {"numeric_match": lambda *_: float("nan")})
    run = execute(RunConfig(tasks=["demo_math"]), catalog(), Store(tmp_path / "runs.db"))
    assert run["status"] == "failed"
    assert run["completed"] == 0
    assert "finite score" in run["error"]
