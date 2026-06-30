"""SQLite persistence for the cluster. One connection, WAL, a lock.

ponytail: single global connection guarded by a lock. Fine for localhost /
dozens of workers. Swap for a pool / PostgreSQL when concurrency demands it
(schema is plain SQL, no SQLite-only column types).
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

_DB_PATH = Path(__file__).parent / "data" / "cluster.db"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS workers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  provider TEXT,
  model TEXT,
  description TEXT,
  personality TEXT,
  skills TEXT,            -- json array
  tools TEXT,             -- json array
  context_window INTEGER,
  max_parallel_tasks INTEGER DEFAULT 1,
  status TEXT DEFAULT 'online',
  heartbeat REAL,
  registered_at REAL
);

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  participants TEXT,      -- json array
  title TEXT,
  created_at REAL,
  updated_at REAL
);

CREATE TABLE IF NOT EXISTS tasks (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT UNIQUE NOT NULL,
  title TEXT,
  description TEXT,
  creator TEXT,
  assigned_worker TEXT,
  required_skill TEXT,
  priority INTEGER DEFAULT 0,
  parent_id TEXT,
  dependencies TEXT,      -- json array of task ids
  status TEXT DEFAULT 'open',   -- open|assigned|in_progress|completed|failed
  conversation_id TEXT,
  result TEXT,
  created_at REAL,
  updated_at REAL
);

CREATE TABLE IF NOT EXISTS messages (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT UNIQUE NOT NULL,
  sender TEXT,
  receiver TEXT,
  conversation_id TEXT,
  task_id TEXT,
  role TEXT,
  content TEXT,
  metadata TEXT,          -- json
  created_at REAL
);

CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT UNIQUE NOT NULL,
  type TEXT,
  actor TEXT,
  ref_id TEXT,
  data TEXT,              -- json
  created_at REAL
);

-- one FTS index across everything searchable; kind+ref_id point back.
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts
  USING fts5(kind, ref_id UNINDEXED, body);
"""


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def now() -> float:
    return time.time()


def execute(sql: str, params: tuple = ()):
    with _lock:
        cur = conn().execute(sql, params)
        conn().commit()
        return cur


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return conn().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def index(kind: str, ref_id: str, body: str):
    """Add/refresh a row in the full-text index."""
    with _lock:
        c = conn()
        c.execute("DELETE FROM search_fts WHERE kind=? AND ref_id=?", (kind, ref_id))
        c.execute(
            "INSERT INTO search_fts(kind, ref_id, body) VALUES (?,?,?)",
            (kind, ref_id, body or ""),
        )
        c.commit()


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k in ("skills", "tools", "participants", "dependencies", "metadata", "data"):
        if k in d and isinstance(d[k], str) and d[k]:
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d
