"""Persistent background jobs — SQLite store + thread runner.

Job lifecycle: queued -> running -> completed | failed | cancelled.
State survives restarts; lab artifacts stay on the filesystem (jobs
only hold metadata + logs, never duplicate domain data).

Concurrency: one active job per `key` (e.g. a research run or an
experiment) — re-submitting while one runs returns the existing job.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  progress REAL DEFAULT 0,
  operation TEXT DEFAULT '',
  logs TEXT DEFAULT '[]',
  error TEXT,
  created REAL, started REAL, finished REAL,
  cancel INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS jobs_key ON jobs(key, status);
"""


class Jobs:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._cancel = {}                     # job_id -> threading.Event

    # ---------- lifecycle ----------
    def submit(self, kind: str, key: str, fn) -> dict:
        """Enqueue `fn(job)` on a daemon thread. `key` dedupes — a
        running/queued job for the same key is returned instead."""
        with self._lock:
            row = self._db.execute(
                "SELECT id FROM jobs WHERE key=? AND status IN "
                "('queued','running')", (key,)).fetchone()
            if row:
                return self.get(row[0])
            jid = f"job-{uuid.uuid4().hex[:10]}"
            self._db.execute(
                "INSERT INTO jobs (id,kind,key,status,created) "
                "VALUES (?,?,?,'queued',?)",
                (jid, kind, key, time.time()))
            self._db.commit()
            ev = threading.Event()
            self._cancel[jid] = ev
        threading.Thread(target=self._run, args=(jid, fn, ev),
                         daemon=True).start()
        return self.get(jid)

    def _run(self, jid: str, fn, ev: threading.Event) -> None:
        self._update(jid, status="running", started=time.time())
        job = _Handle(self, jid, ev)
        try:
            fn(job)
        except _Cancelled:
            self._update(jid, status="cancelled",
                         finished=time.time())
        except Exception as e:  # noqa: BLE001 - record, never crash worker
            self._update(jid, status="failed", error=str(e),
                         finished=time.time())
        else:
            self._update(jid, status="completed", progress=1.0,
                         finished=time.time())
        finally:
            self._cancel.pop(jid, None)

    # ---------- accessors ----------
    def get(self, jid: str) -> dict:
        r = self._db.execute("SELECT * FROM jobs WHERE id=?",
                             (jid,)).fetchone()
        return self._row(r) if r else {}

    def list(self, limit: int = 50) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM jobs ORDER BY created DESC LIMIT ?",
            (limit,)).fetchall()
        return [self._row(r) for r in rows]

    def cancel(self, jid: str) -> dict:
        ev = self._cancel.get(jid)
        if ev:
            ev.set()
        self._db.execute(
            "UPDATE jobs SET cancel=1 WHERE id=? AND status IN "
            "('queued','running')", (jid,))
        self._db.commit()
        j = self.get(jid)
        if j.get("status") == "queued":
            self._update(jid, status="cancelled", finished=time.time())
            j = self.get(jid)
        return j

    # ---------- internals ----------
    def _update(self, jid: str, **kv) -> None:
        with self._lock:
            sets = ", ".join(f"{k}=?" for k in kv)
            self._db.execute(f"UPDATE jobs SET {sets} WHERE id=?",
                             (*kv.values(), jid))
            self._db.commit()

    def _log(self, jid: str, line: str) -> None:
        with self._lock:
            logs = json.loads(self._db.execute(
                "SELECT logs FROM jobs WHERE id=?", (jid,)
            ).fetchone()[0])
            logs.append(line[:500])
            self._db.execute("UPDATE jobs SET logs=? WHERE id=?",
                             (json.dumps(logs[-200:]), jid))
            self._db.commit()

    @staticmethod
    def _row(r) -> dict:
        keys = ("id", "kind", "key", "status", "progress", "operation",
                "logs", "error", "created", "started", "finished",
                "cancel")
        d = dict(zip(keys, r))
        d["logs"] = json.loads(d["logs"] or "[]")
        return d


class _Cancelled(Exception):
    pass


class _Handle:
    """Passed to job functions: progress/log/cancel surface."""

    def __init__(self, store: Jobs, jid: str, ev: threading.Event):
        self._s, self.id, self._ev = store, jid, ev

    def progress(self, frac: float, operation: str = "") -> None:
        self._s._update(self.id, progress=min(max(frac, 0), 1),
                        operation=operation[:200])
        if self._ev.is_set():
            raise _Cancelled()

    def log(self, line: str) -> None:
        self._s._log(self.id, line)
        if self._ev.is_set():
            raise _Cancelled()

    @property
    def cancelled(self) -> bool:
        return self._ev.is_set()
