"""Persistent background jobs — SQLite store + bounded thread pool.

Lifecycle: queued -> running -> completed | failed | cancelled |
interrupted | timeout. State survives restarts; lab artifacts stay on
the filesystem — jobs hold metadata + logs only, never domain data.

Recovery policy (honest, per spec): a worker thread cannot outlive its
process, so on startup every job still 'queued'/'running' is marked
'interrupted' — never silently completed. Resumable kinds
(deep-research) pick up where their domain state left off when the
caller submits a fresh job; there is no transparent resume of a dead
callable.

Concurrency: ThreadPoolExecutor(max_workers). A job `key` may have at
most one active job — enforced by a partial UNIQUE index, so duplicate
submission races return the existing job rather than spawning a second.

Timeouts are cooperative: an expired job's cancel event is set and its
status becomes 'timeout'; the worker observes it at the next
log()/progress()/cancelled checkpoint and aborts (Python threads
cannot be force-killed safely).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK(status IN ('queued','running','completed','failed',
                     'cancelled','interrupted','timeout')),
  progress REAL DEFAULT 0,
  operation TEXT DEFAULT '',
  logs TEXT DEFAULT '[]',
  error TEXT,
  timeout_s REAL,
  created REAL, started REAL, finished REAL,
  cancel INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS jobs_key ON jobs(key, status);
-- at most one active job per key, enforced atomically
CREATE UNIQUE INDEX IF NOT EXISTS jobs_active_key
  ON jobs(key) WHERE status IN ('queued','running');
"""

_ACTIVE = ("queued", "running")
DEFAULT_TIMEOUT = 3600.0
MAX_WORKERS = 4
_LOG_CAP = 200


class Jobs:
    def __init__(self, db_path: Path, max_workers: int = MAX_WORKERS):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False,
                                   timeout=30)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=30000")
        self._db.executescript(_SCHEMA)
        self._migrate()
        # RLock: one shared connection means EVERY execute/transaction
        # must hold the lock — with conn: blocks interleaving across
        # threads corrupt sqlite3's transaction state (observed as
        # intermittent InterfaceError). Reentrant so helpers can nest.
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="skilllab-job")
        self._cancel: dict[str, threading.Event] = {}
        self._recover()

    def _migrate(self) -> None:
        """Bring an older jobs.db forward without losing history —
        ALTER add new columns; never drop the table."""
        cols = {r[1] for r in
                self._db.execute("PRAGMA table_info(jobs)")}
        for col, ddl in (("timeout_s", "REAL"),
                         ("cancel", "INTEGER DEFAULT 0")):
            if col not in cols:
                self._db.execute(
                    f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")
        self._db.commit()

    # ---------- recovery ----------
    def _recover(self) -> None:
        """Crash/restart: workers died with the process. Mark every
        still-active job 'interrupted' — honest, resumable kinds are
        re-submitted by their callers."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE jobs SET status='interrupted', finished=?, "
                "error=COALESCE(error,'worker process died') "
                "WHERE status IN ('queued','running')",
                (time.time(),))

    # ---------- lifecycle ----------
    # bound on check+insert cycles when the insert keeps losing the
    # unique-index race to another connection (see submit docstring)
    SUBMIT_ATTEMPTS = 50
    SUBMIT_RETRY_S = 0.025

    def _insert(self, jid: str, kind: str, key: str,
                timeout_s: float) -> None:
        """One queued-row insert — the atomic uniqueness checkpoint.
        Kept tiny so tests can inject a deterministic IntegrityError."""
        with self._db:
            self._db.execute(
                "INSERT INTO jobs (id,kind,key,status,created,"
                "timeout_s) VALUES (?,?,?,'queued',?,?)",
                (jid, kind, key, time.time(), timeout_s))

    def submit(self, kind: str, key: str, fn,
               timeout_s: float = DEFAULT_TIMEOUT) -> dict:
        """Enqueue `fn(job_handle)`; returns the existing active job for
        `key` when one exists (the UNIQUE index makes this atomic —
        a losing insert race returns the winner's job).

        The unique-index conflict path needs care: a conflicting insert
        means a queued/running row for `key` exists on *some* connection
        — another Jobs instance or process sharing this db file; the
        in-process lock already serializes same-instance submits. That
        competitor may finish in the window between our failed insert
        and the follow-up query, so the whole check+insert runs as a
        bounded retry cycle instead of a single recheck:

          winner still active -> return its record;
          winner finished     -> its index entry is gone, insert wins;
          conflict persists   -> raise JobSubmitError.

        Submit therefore NEVER returns {} — a caller either gets a real
        job record or an exception."""
        for attempt in range(self.SUBMIT_ATTEMPTS):
            if attempt:
                # outside the lock — let workers/checkpoints breathe
                time.sleep(self.SUBMIT_RETRY_S)
            with self._lock:
                row = self._db.execute(
                    "SELECT id FROM jobs WHERE key=? AND status IN "
                    "('queued','running')", (key,)).fetchone()
                if row:
                    return self.get(row[0])
                jid = f"job-{uuid.uuid4().hex[:10]}"
                try:
                    self._insert(jid, kind, key, timeout_s)
                except sqlite3.IntegrityError:
                    continue          # winner exists — recheck next pass
                ev = threading.Event()
                self._cancel[jid] = ev
            self._pool.submit(self._run, jid, fn, ev)
            return self.get(jid)
        raise JobSubmitError(
            f"could not submit job for key {key!r}: persistent "
            "uniqueness conflict in the jobs store — retry")

    def _run(self, jid: str, fn, ev: threading.Event) -> None:
        if not self._transition(jid, "queued", "running",
                                started=time.time()):
            return                             # cancelled while queued
        job = _Handle(self, jid, ev)
        deadline = time.monotonic() + (self.get(jid).get("timeout_s")
                                       or DEFAULT_TIMEOUT)
        try:
            fn(job)
            if job.cancelled:
                self._finish(jid, "cancelled")
            elif time.monotonic() > deadline:
                self._finish(jid, "timeout",
                             error="job exceeded its timeout")
            else:
                self._finish(jid, "completed", progress=1.0)
        except _Cancelled:
            pass                               # status already terminal
        except TimeoutError:
            self._finish(jid, "timeout", error="job exceeded its timeout")
        except Exception as e:  # noqa: BLE001 - record, never crash pool
            self._finish(jid, "failed",
                         error=f"{type(e).__name__}: {e}")
        finally:
            self._cancel.pop(jid, None)

    def _finish(self, jid: str, status: str, **kv) -> None:
        kv.setdefault("finished", time.time())
        self._update_if_active(jid, status, **kv)

    # ---------- accessors ----------
    def get(self, jid: str) -> dict:
        with self._lock:
            r = self._db.execute("SELECT * FROM jobs WHERE id=?",
                                 (jid,)).fetchone()
            return self._row(r) if r else {}

    def list(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM jobs ORDER BY created DESC LIMIT ?",
                (limit,)).fetchall()
            return [self._row(r) for r in rows]

    def cancel(self, jid: str) -> dict:
        with self._lock:
            j = self.get(jid)
            if not j or j["status"] not in _ACTIVE:
                return j
            ev = self._cancel.get(jid)
            if ev:
                ev.set()                       # running: cooperative
            if j["status"] == "queued":
                # may still flip to running — the worker checks
                self._db.execute(
                    "UPDATE jobs SET status='cancelled', finished=? "
                    "WHERE id=? AND status='queued'",
                    (time.time(), jid))
                self._db.commit()
            else:
                self._db.execute(
                    "UPDATE jobs SET cancel=1 WHERE id=?", (jid,))
                self._db.commit()
            return self.get(jid)

    # ---------- internals ----------
    def _transition(self, jid: str, frm: str, to: str, **kv) -> bool:
        sets = ", ".join(f"{k}=?" for k in ("status", *kv))
        with self._lock, self._db:
            cur = self._db.execute(
                f"UPDATE jobs SET {sets} WHERE id=? AND status=?",
                (to, *kv.values(), jid, frm))
            return cur.rowcount == 1

    def _update_if_active(self, jid: str, status: str, **kv) -> None:
        sets = ", ".join(f"{k}=?" for k in ("status", *kv))
        with self._lock, self._db:
            self._db.execute(
                f"UPDATE jobs SET {sets} WHERE id=? AND status IN "
                "('queued','running')", (status, *kv.values(), jid))

    def _checkpoint(self, jid: str, ev: threading.Event) -> None:
        """Raise _Cancelled when the job was cancelled or timed out
        (checked against both the event and the db flag — cancel() also
        works if the event map entry is gone)."""
        if ev.is_set():
            raise _Cancelled()
        with self._lock:
            row = self._db.execute(
                "SELECT status, cancel, timeout_s, started FROM jobs "
                "WHERE id=?", (jid,)).fetchone()
        if row is None:
            raise _Cancelled()
        status, cancel, tmo, started = row
        if status in ("cancelled", "failed", "completed",
                      "interrupted", "timeout"):
            raise _Cancelled()
        if cancel:
            self._finish(jid, "cancelled")
            ev.set()
            raise _Cancelled()
        if tmo and started and \
                time.time() - started > tmo:
            self._finish(jid, "timeout", error="job exceeded its timeout")
            ev.set()
            raise _Cancelled()

    def _log(self, jid: str, line: str) -> None:
        with self._lock, self._db:
            logs = json.loads(self._db.execute(
                "SELECT logs FROM jobs WHERE id=?", (jid,)
            ).fetchone()[0])
            logs.append(line[:500])
            self._db.execute("UPDATE jobs SET logs=? WHERE id=?",
                             (json.dumps(logs[-_LOG_CAP:]), jid))

    @staticmethod
    def _row(r) -> dict:
        keys = ("id", "kind", "key", "status", "progress", "operation",
                "logs", "error", "timeout_s", "created", "started",
                "finished", "cancel")
        d = dict(zip(keys, r))
        d["logs"] = json.loads(d["logs"] or "[]")
        return d


class JobSubmitError(RuntimeError):
    """Raised when a job cannot be enqueued — a persistent uniqueness
    conflict means the jobs store cannot honestly identify the job that
    should own the key. Mapped to HTTP 503 by the app (retry-safe)."""


class _Cancelled(Exception):
    pass


class _Handle:
    """Passed to job functions: progress/log/cancel surface. Every
    method is also a cancellation checkpoint."""

    def __init__(self, store: Jobs, jid: str, ev: threading.Event):
        self._s, self.id, self._ev = store, jid, ev

    def progress(self, frac: float, operation: str = "") -> None:
        self._s._update_if_active(
            self.id, "running", progress=min(max(frac, 0), 1),
            operation=operation[:200])
        self._s._checkpoint(self.id, self._ev)

    def log(self, line: str) -> None:
        self._s._log(self.id, line)
        self._s._checkpoint(self.id, self._ev)

    @property
    def cancelled(self) -> bool:
        return self._ev.is_set()
