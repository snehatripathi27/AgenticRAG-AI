"""SQLite is the source of truth for configurations, runs, and sample logs."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, config TEXT NOT NULL,
              results TEXT NOT NULL DEFAULT '{}', manifest TEXT NOT NULL DEFAULT '{}',
              completed INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
              error TEXT, duration REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS samples (
              run_id TEXT NOT NULL REFERENCES runs(id), task TEXT NOT NULL, sample_id TEXT NOT NULL,
              data TEXT NOT NULL, PRIMARY KEY(run_id,task,sample_id));
            CREATE TABLE IF NOT EXISTS configs (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, config TEXT NOT NULL, created_at TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, config):
        run_id = uuid4().hex[:12]
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs(id,name,status,created_at,updated_at,config) VALUES (?,?,?,?,?,?)",
                (run_id, config.name, "queued", now(), now(), config.model_dump_json()),
            )
        return run_id

    def update(self, run_id, **fields):
        allowed = {"status", "results", "manifest", "completed", "total", "error", "duration"}
        if not fields.keys() <= allowed:
            raise ValueError("Invalid run field")
        fields["updated_at"] = now()
        values = [json.dumps(v, allow_nan=False) if isinstance(v, dict) else v for v in fields.values()]
        with self.connect() as db:
            db.execute(f"UPDATE runs SET {','.join(f'{k}=?' for k in fields)} WHERE id=?", [*values, run_id])

    def add_samples(self, run_id, samples):
        with self.connect() as db:
            db.executemany(
                "INSERT INTO samples VALUES (?,?,?,?)",
                [(run_id, s["task"], s["sample_id"], json.dumps(s, allow_nan=False)) for s in samples],
            )
            db.execute(
                "UPDATE runs SET completed=(SELECT COUNT(*) FROM samples WHERE run_id=?), updated_at=? WHERE id=?",
                (run_id, now(), run_id),
            )

    @staticmethod
    def decode(row):
        if row is None:
            return None
        result = dict(row)
        for key in ("config", "results", "manifest"):
            if key in result:
                result[key] = json.loads(result[key])
        return result

    def get(self, run_id):
        with self.connect() as db:
            return self.decode(db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())

    def runs(self):
        with self.connect() as db:
            return [
                self.decode(r) for r in db.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 200")
            ]

    def samples(self, run_id, limit=1000, offset=0):
        with self.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT data FROM samples WHERE run_id=? ORDER BY rowid LIMIT ? OFFSET ?",
                    (run_id, limit, offset),
                )
            ]

    def interrupt_pending(self):
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET status='interrupted', error='Server stopped before completion', updated_at=? WHERE status IN ('running','queued')",
                (now(),),
            )

    def save_config(self, config):
        id_ = uuid4().hex[:12]
        with self.connect() as db:
            db.execute(
                "INSERT INTO configs VALUES (?,?,?,?)", (id_, config.name, config.model_dump_json(), now())
            )
        return id_

    def configs(self):
        with self.connect() as db:
            return [self.decode(r) for r in db.execute("SELECT * FROM configs ORDER BY created_at DESC")]
