# Verification record

Verified in the development sandbox on 2026-10-06.

## Passed

- **46 Python tests:** configuration validation; task/prompt boundaries; metric parsing and plugin registration; deterministic runs; partial failures and redaction; SQLite persistence; API lifecycle and pagination; CLI exports/exit codes; HF, vLLM, HTTP, and dataset adapter contracts.
- **Real CPU inference:** `hf-internal-testing/tiny-random-gpt2` completed two synthetic samples, then ten samples across ARC Easy, ARC Challenge, BoolQ, GSM8K, and HellaSwag. These are execution smoke tests, not quality claims about the tiny random model.
- **CLI demo:** 28 samples completed; full JSON export contains all predictions, references, prompts, metrics, and manifest data.
- **Packaging:** wheel and source distribution built successfully.
- **Python lint:** `ruff check src tests`.
- **Frontend:** TypeScript/production build and `eslint src/App.tsx src/icons.ts` pass. Production bundle is about 221 kB JavaScript (70 kB gzip).
- **Shared browser:** launch a run; validate invalid/valid configs; save and reuse config; compare two runs; inspect/paginate sample logs (20 + 8); download and verify all 28 sample logs; filter the task catalog; reload persisted data. Desktop and 390 px mobile layouts inspected, without horizontal page overflow. No browser errors observed.
- **Accessibility:** automated axe scan on the overview reports zero violations after contrast and table-header fixes. This is a limited automated scan, not a full accessibility certification.
- **Runtime dependency audit:** `npm audit --omit=dev` reports zero advisories.

## Limits

- vLLM has adapter contract coverage; real accelerated inference was not run because CUDA is unavailable in this sandbox.
- HTTP provider calls have synthetic transport tests for payload shape, retries, malformed output, and error handling. No live provider inference was run. CodeRabbit emulate v0.0.1 was installed and its catalog checked; it does not provide chat-completion inference.
- Eight inherited frontend **development dependency** advisories remain in the Tailwind 3 dependency graph (six high, two moderate). Nonbreaking updates reduced the original 32 advisories. Resolving the remaining graph requires a separate Tailwind migration; no forced major upgrade was applied.
- Starlette emits a deprecation warning for its current httpx-based test client; tests pass.
- Single-user local deployment only; production authentication and a durable distributed queue are outside this implementation.

## Build compatibility

Rollup 4.64.0 caused a sustained tree-shaking slowdown in this environment. The frontend pins 4.59.0 through npm overrides and imports only the icons it uses; the final production build completes in roughly 1.5 seconds. Retain the committed lockfile for repeatable builds.
