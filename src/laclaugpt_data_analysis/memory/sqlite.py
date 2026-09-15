"""SQLite-backed persistent analysis memory."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import MemoryEntry


class SQLiteMemoryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS memory_entries ("
                "entry_id TEXT PRIMARY KEY, namespace TEXT NOT NULL, "
                "canonical_label TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    def put(self, entry: MemoryEntry) -> None:
        with sqlite3.connect(self.path) as con:
            con.execute(
                "INSERT INTO memory_entries(entry_id, namespace, canonical_label, payload) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(entry_id) DO UPDATE SET "
                "namespace=excluded.namespace, canonical_label=excluded.canonical_label, payload=excluded.payload",
                (entry.entry_id, entry.namespace, entry.canonical_label, entry.model_dump_json()),
            )

    def get(self, entry_id: str) -> MemoryEntry | None:
        with sqlite3.connect(self.path) as con:
            row = con.execute("SELECT payload FROM memory_entries WHERE entry_id = ?", (entry_id,)).fetchone()
        return MemoryEntry.model_validate_json(row[0]) if row else None

    def all(self, namespace: str | None = None) -> list[MemoryEntry]:
        with sqlite3.connect(self.path) as con:
            if namespace:
                rows = con.execute("SELECT payload FROM memory_entries WHERE namespace = ? ORDER BY canonical_label", (namespace,)).fetchall()
            else:
                rows = con.execute("SELECT payload FROM memory_entries ORDER BY namespace, canonical_label").fetchall()
        return [MemoryEntry.model_validate_json(row[0]) for row in rows]

    def export_json(self) -> str:
        return json.dumps([entry.model_dump(mode="json") for entry in self.all()], ensure_ascii=False, sort_keys=True)
