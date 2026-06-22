"""翻译历史记录（SQLite）。"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass

from llm_translator.storage import paths


@dataclass
class Entry:
    src: str
    tgt: str
    source_text: str
    target_text: str
    provider: str
    id: int | None = None
    timestamp: float = 0.0


class HistoryStore:
    def __init__(self) -> None:
        self._db = paths.history_file()
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    src TEXT NOT NULL,
                    tgt TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    target_text TEXT NOT NULL,
                    provider TEXT NOT NULL
                )
                """
            )

    def add(self, entry: Entry) -> None:
        entry.timestamp = entry.timestamp or time.time()
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO translations (timestamp, src, tgt, source_text, target_text, provider) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (entry.timestamp, entry.src, entry.tgt, entry.source_text, entry.target_text, entry.provider),
            )
            entry.id = cur.lastrowid

    def _row_to_entry(self, row: sqlite3.Row) -> Entry:
        return Entry(
            id=row["id"],
            timestamp=row["timestamp"],
            src=row["src"],
            tgt=row["tgt"],
            source_text=row["source_text"],
            target_text=row["target_text"],
            provider=row["provider"],
        )

    def list(self, limit: int = 50, offset: int = 0) -> list[Entry]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT * FROM translations ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            return [self._row_to_entry(r) for r in cur.fetchall()]

    def search(self, query: str, limit: int = 50) -> list[Entry]:
        like = f"%{query}%"
        with self._conn() as c:
            cur = c.execute(
                "SELECT * FROM translations WHERE source_text LIKE ? OR target_text LIKE ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (like, like, limit),
            )
            return [self._row_to_entry(r) for r in cur.fetchall()]

    def clear(self) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM translations")
