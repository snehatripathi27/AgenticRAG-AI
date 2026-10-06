# BenchLab

Repeatable language model evaluations, from your terminal to a local React workspace.

BenchLab includes a Python evaluation engine, CLI, FastAPI service, SQLite run history, and a React/TypeScript interface. Pick a model and tasks, save a configuration, then inspect scores and every generated answer. The bundled offline demo exercises the full workflow without downloading weights or using credentials.

## Install

Requires **Python 3.10+**. The web interface also requires **Node 22.12+** and npm. Python 3.12 and Node 24 are used for development.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cd frontend
npm ci
cd ..
```

Only install inference dependencies when you need them:

| Backend | Install | Requirements |
| --- | --- | --- |
| Offline demo | Base installation | Deterministic toy baseline, not a language model |
| Hugging Face | `pip install -e '.[hf,benchmarks]'` | CPU or supported GPU; model weights and dataset access |
| vLLM | `pip install -e '.[vllm,benchmarks]'` | A vLLM-supported accelerator and platform; use a separate environment when its Torch requirements differ |
| Compatible HTTP API | `pip install -e '.[benchmarks]'` | Chat Completions endpoint and API key environment variable |

## Run a complete demo

```bash
source .venv/bin/activate
benchlab tasks
benchlab validate examples/demo.yaml
benchlab run --config examples/demo.yaml --output .benchlab/demo.json
bash scripts/demo.sh
```

Open **http://localhost:5173**. The script starts the API at `127.0.0.1:8001`, then the frontend at `localhost:5173`. Ctrl+C stops both. It creates an initial demo run only when the database is empty. The workspace supports:

- Model/task selection with guided and JSON configuration editors
- Config validation, saving, downloading, and reuse
- Background runs with polling, status, and sample counts
- Task scores, per-sample prompts/responses/references, and pagination
- Run comparisons, searching, and JSON export of summaries or complete logs
- A task catalog and built-in usage guide

The demo model performs arithmetic, recognizes a small set of facts, and uses seeded choices for reasoning. All demo data is synthetic. These scores must not be presented as results from a real language model.

### CLI

```bash
benchlab tasks --json
benchlab run --backend hf --model Qwen/Qwen2.5-0.5B-Instruct \
  --tasks arc_easy boolq --limit 100 --seed 42
benchlab run --config examples/huggingface.yaml --limit 10
benchlab results
benchlab results RUN_ID --format json
benchlab results RUN_ID --format jsonl > predictions.jsonl
benchlab --db ./experiment.db run --config examples/demo.yaml
benchlab --task-dir examples/tasks tasks
```

Global flags (`--db`, `--task-dir`) precede the command. Command flags override matching config fields. Run IDs are printed on completion. Exit codes: `0` success, `1` an evaluation failed (logs retained), `2` invalid configuration or usage. Use `benchlab COMMAND --help` for all options.

### Configuration

```yaml
name: Science baseline
model:
  backend: hf                 # demo | hf | vllm | api
  name: Qwen/Qwen2.5-0.5B-Instruct
  # revision: immutable-model-commit
  device: auto
  temperature: 0
  max_tokens: 32
tasks: [arc_easy, arc_challenge]
seed: 42
limit: 100                    # maximum samples per task
batch_size: 4
# dataset_revisions:
#   arc_easy: immutable-dataset-commit
# prompts:
#   arc_easy: "{question}\n{choices}\nAnswer with one letter:"
```

`validate` checks structure, bounds, task and metric names, duplicate tasks, and prompt placeholders without downloading a model or dataset. It does not promise that a provider is reachable or that hardware is sufficient. YAML uses safe loading; unknown fields are rejected.

For API models, use `examples/api.yaml`, change `model.name` and `base_url`, and set the environment variable named by `api_key_env` on the **server process**. Never put a secret value in configuration. The adapter sends `model`, `messages`, `temperature`, `max_tokens`, and `seed` to `/chat/completions`; select a provider/model supporting that contract. It retries transient connection errors, 429s, and 5xx responses up to three attempts.

## Built-in benchmarks

| Task | Dataset / split | Metric |
| --- | --- | --- |
| `arc_easy` | allenai/ai2_arc, ARC-Easy / test | Choice accuracy |
| `arc_challenge` | allenai/ai2_arc, ARC-Challenge / test | Choice accuracy |
| `hellaswag` | Rowan/hellaswag / validation | Choice accuracy |
| `boolq` | google/boolq / validation | Normalized exact match (yes/no) |
| `gsm8k` | openai/gsm8k, main / test | Final numeric answer match |
| `demo_reasoning`, `demo_math`, `demo_knowledge` | Bundled synthetic samples | Choice / numeric / exact match |

Standard datasets are downloaded on demand using the `benchmarks` extra. Dataset authors' access conditions and licenses apply. BenchLab uses **generated-answer evaluation**, not likelihood ranking or canonical leaderboard protocols. HellaSwag/ARC scores therefore are not directly comparable to likelihood-based benchmark reports. No user-supplied generated code is executed.

## Extend without changing the engine

Add a YAML file and JSONL samples to a task directory. See [`examples/tasks`](examples/tasks) and [`docs/evaluation.md`](docs/evaluation.md).

```yaml
id: capitals
title: World capitals
metric: exact_match
prompt: 'Answer with only the city name: {question}'
data_file: capitals.jsonl
```

```json
{"id":"fr","question":"What is the capital of France?","reference":"Paris"}
```

Run or serve with `benchlab --task-dir examples/tasks ...`. Configs select the new task by ID. Prompt placeholders support `{question}`, `{context}`, and `{choices}` only; references are never given to inference backends. Built-in metrics include `exact_match`, `choice_accuracy`, `numeric_match`, and `token_f1`. Installed Python packages can register metric functions through the `benchlab.metrics` entry-point group.

## API and storage

```bash
benchlab serve --host 127.0.0.1 --port 8001
# Separate terminal:
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
```

Interactive API reference: **http://localhost:8001/api/docs** (also available through the frontend proxy at `/api/docs`). See [`docs/api.md`](docs/api.md).

Runs, validated configurations, sample logs, and reproducibility manifests are persisted to `.benchlab/runs.db` by default. API executions use a single background worker to prevent concurrent local model loads. Incomplete jobs are marked `interrupted` after restart; resume by reusing the configuration. Keep CLI runs and the server on separate database files if executing simultaneously or restarting the server during a CLI run. Run history lists the most recent 200 evaluations; older runs remain accessible by ID.

This is a **trusted local developer tool**. There is no authentication, multi-user isolation, distributed scheduling, or durable queue. Bind the API to loopback; add authentication and access controls before exposing it to other users. Provider endpoints and installed metric plugins are trusted administrator configuration. Logs can contain input data and generated text; store/export them accordingly.

## Development and verification

```bash
pytest -q
ruff check src tests
python -m build
cd frontend
npm run build
npx eslint src/App.tsx
```

Tests cover repeatability, data adapters, scoring, prompt boundaries, invalid configs, partial failures, persistence, API lifecycle, and CLI exports. Adapter contract tests use synthetic responses; running actual accelerator/provider inference remains environment dependent. The API and UI demo require no external service.

```text
src/benchlab/     config, tasks, metrics, model adapters, runner, storage, API, CLI
frontend/        React + TypeScript workspace
examples/        reusable configurations and custom task examples
tests/           deterministic unit and integration tests
docs/            evaluation protocol, API, and historical RAG documentation
scripts/         local demo startup
```

The repository's prior RAG backend and components are retained. Its historical setup lives in [`docs/legacy-rag.md`](docs/legacy-rag.md); root `requirements.txt` and the earlier RAG guides belong to that application and are **not** needed for BenchLab.

See [verification results and environment limits](docs/verification.md) for the tested backends, browser flows, and outstanding development dependency advisories.
