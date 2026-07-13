"""Dictation history in SQLite (%APPDATA%\\FlowLocal\\history.db).

Each dictation stores both raw and cleaned text so nothing is ever lost.
status: "cleaned" | "raw_fallback" | "cleanup_off" | "error"
"""
import sqlite3
import threading
import time

from .config import APP_DIR

DB_PATH = APP_DIR / "history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    language TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    cleaned_text TEXT,
    target_app TEXT,
    duration_ms INTEGER,
    status TEXT NOT NULL
)
"""


class History:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # written from worker, read from UI thread
        self._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def add(
        self,
        language: str,
        raw_text: str,
        cleaned_text: str | None,
        target_app: str,
        duration_ms: int,
        status: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO history (ts, language, raw_text, cleaned_text, target_app, duration_ms, status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (time.time(), language, raw_text, cleaned_text, target_app, duration_ms, status),
            )
            self._conn.commit()

    def recent(self, limit: int = 200) -> list[tuple]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, ts, language, raw_text, cleaned_text, target_app, duration_ms, status"
                " FROM history ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM history")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
