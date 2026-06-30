"""sqlite persistence for memory. Thin CRUD; no business logic.

A single connection is shared across daemon worker threads, guarded by a lock.
"""
import sqlite3
import threading
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT, text TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL, text TEXT NOT NULL,
    created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, text TEXT NOT NULL, ok INTEGER NOT NULL, summary TEXT);
"""


class Store:
    def __init__(self, path: "Path | str") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # --- facts ---
    def add_fact(self, text: str, key: "str | None" = None, *, now: float) -> None:
        with self._lock:
            if key is not None:
                self._conn.execute("DELETE FROM facts WHERE key = ?", (key,))
            self._conn.execute(
                "INSERT INTO facts (key, text, created_at) VALUES (?, ?, ?)",
                (key, text, now))
            self._conn.commit()

    def list_facts(self) -> list:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, key, text FROM facts ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [(r["id"], r["key"], r["text"]) for r in rows]

    def delete_fact(self, *, id: "int | None" = None, key: "str | None" = None) -> bool:
        with self._lock:
            if id is not None:
                cur = self._conn.execute("DELETE FROM facts WHERE id = ?", (id,))
            else:
                cur = self._conn.execute("DELETE FROM facts WHERE key = ?", (key,))
            self._conn.commit()
            return cur.rowcount > 0

    # --- notes ---
    def upsert_note(self, key: str, text: str, *, now: float) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO notes (key, text, created_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       text = excluded.text, updated_at = excluded.updated_at""",
                (key, text, now, now))
            self._conn.commit()

    def get_note(self, key: str) -> "str | None":
        with self._lock:
            row = self._conn.execute(
                "SELECT text FROM notes WHERE key = ?", (key,)).fetchone()
        return row["text"] if row else None

    def search_notes(self, query: str) -> list:
        like = f"%{query}%"
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, text FROM notes WHERE key LIKE ? OR text LIKE ?",
                (like, like)).fetchall()
        return [(r["key"], r["text"]) for r in rows]

    def delete_note(self, key: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM notes WHERE key = ?", (key,))
            self._conn.commit()
            return cur.rowcount > 0

    # --- turns ---
    def add_turn(self, role: str, text: str, ts: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO turns (ts, role, text) VALUES (?, ?, ?)",
                (ts, role, text))
            self._conn.commit()

    def turns_since(self, ts: float) -> list:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, text FROM turns WHERE ts >= ? ORDER BY ts ASC, id ASC",
                (ts,)).fetchall()
        return [(r["role"], r["text"]) for r in rows]

    # --- commands ---
    def add_command(self, text: str, ok: bool, summary: str, ts: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO commands (ts, text, ok, summary) VALUES (?, ?, ?, ?)",
                (ts, text, 1 if ok else 0, summary))
            self._conn.commit()
