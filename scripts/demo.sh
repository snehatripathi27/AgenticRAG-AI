#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/benchlab || ! -d frontend/node_modules ]]; then
  echo "Install first: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' && (cd frontend && npm ci)" >&2
  exit 1
fi
.venv/bin/python - <<'PY'
import socket
from benchlab.config import RunConfig
from benchlab.runner import execute
from benchlab.storage import Store
from benchlab.tasks import catalog
for port in (8001, 5173):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('127.0.0.1', port))
        except OSError:
            raise SystemExit(f'Port {port} is already in use. Stop that service first.')
store = Store('.benchlab/runs.db')
if not store.runs():
    result = execute(RunConfig(name='Getting started · demo'), catalog(), store)
    if result['status'] != 'completed':
        raise SystemExit(result['error'])
PY
.venv/bin/benchlab serve --host 127.0.0.1 --port 8001 &
benchlab_api_pid=$!
trap 'kill "$benchlab_api_pid" 2>/dev/null || true' EXIT INT TERM
.venv/bin/python - "$benchlab_api_pid" <<'PY'
import os, sys, time, urllib.request
for _ in range(100):
    try:
        os.kill(int(sys.argv[1]), 0)
        with urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=1) as response:
            if response.status == 200:
                break
    except (OSError, ValueError):
        time.sleep(.1)
else:
    raise SystemExit('API failed to start. Check port 8001 and server output.')
PY
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
