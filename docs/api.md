# Local HTTP API

Run `benchlab serve`. The Vite frontend proxies `/api` to `127.0.0.1:8001`. Interactive docs: `/api/docs`; schema: `/api/openapi.json`.

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/health` | Readiness/version |
| GET | `/api/tasks` | Built-in/custom task metadata |
| POST | `/api/configs/validate` | Validate/normalize RunConfig |
| POST | `/api/configs` | Persist valid config (201) |
| GET | `/api/configs` | Saved configs, newest first |
| POST | `/api/configs/yaml` | Validate/serialize YAML |
| POST | `/api/runs` | Validate/enqueue RunConfig (202) |
| GET | `/api/runs` | Latest 200 runs |
| GET | `/api/runs/{id}` | Status, scores, counts, config, manifest, error |
| GET | `/api/runs/{id}/samples` | Logs: `limit` 1–1000 (default 100), `offset` ≥0 |

```bash
curl -X POST http://127.0.0.1:8001/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"name":"Demo","model":{"backend":"demo","name":"demo-baseline"},"tasks":["demo_math"],"limit":5}'
curl http://127.0.0.1:8001/api/runs/RUN_ID
```

Statuses: `queued` → `running` → `completed` / `failed`; unfinished jobs become `interrupted` on restart. Retry by reusing the config. Config errors return 422; missing IDs return 404. Failed runs retain sanitized errors and completed samples. A queued response does not verify hardware, installed weights, or credentials.

No wildcard CORS. Use the same-origin proxy. This is a trusted local API without authentication. Bind to loopback; secure it before sharing. Run one API instance per database, and avoid server restarts during CLI runs sharing that database. SQLite WAL and foreign keys are enabled. Tables are `runs`, `samples`, and `configs`. Completed batches and counters commit atomically. JSON values reject NaN/Infinity. Back up via SQLite backup APIs or stop the server before copying the database; copying the `.db` alone during WAL writes can omit data.
