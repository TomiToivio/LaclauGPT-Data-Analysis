"""SQLite-backed stable-ID memory with deterministic alias resolution."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import MemoryRef, Resolution, display_label, normalize


class SQLiteMemory:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS objects ("
                "obj_id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, "
                "norm TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'PROVISIONAL', "
                "provenance TEXT NOT NULL DEFAULT '')"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS aliases ("
                "norm TEXT NOT NULL, obj_id TEXT NOT NULL, UNIQUE(norm, obj_id))"
            )

    def resolve(self, raw: str, kind: str) -> Resolution:
        norm = normalize(raw)
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT o.obj_id, o.label FROM aliases a "
                "JOIN objects o ON o.obj_id = a.obj_id "
                "WHERE a.norm = ? AND o.kind = ? "
                "AND o.state NOT IN ('REJECTED', 'MERGED')",
                (norm, kind),
            ).fetchone()
        if row:
            return Resolution(
                raw=raw,
                kind=kind,
                obj_id=row[0],
                label=row[1],
                decision="EXISTING",
                matched_via="alias",
                score=1.0,
            )
        return Resolution(raw=raw, kind=kind, decision="NEW")

    def resolve_accepted(self, raw: str, kind: str) -> Resolution:
        """Resolve only researcher-accepted canonical memory objects.

        Unlike ``resolve``, this is safe for automatic runtime normalization:
        provisional objects remain visible for review but are never attached to
        Phase 1 output as accepted continuity identifiers.
        """
        norm = normalize(raw)
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT o.obj_id, o.label FROM aliases a "
                "JOIN objects o ON o.obj_id = a.obj_id "
                "WHERE a.norm = ? AND o.kind = ? AND o.state = 'CANONICAL'",
                (norm, kind),
            ).fetchone()
        if row:
            return Resolution(raw=raw, kind=kind, obj_id=row[0], label=row[1], decision="EXISTING", matched_via="alias", score=1.0)
        return Resolution(raw=raw, kind=kind, decision="NEW")

    def create(
        self,
        obj_id: str,
        kind: str,
        label: str,
        provenance: str = "",
    ) -> MemoryRef:
        norm = normalize(label)
        canonical_label = display_label(norm, kind)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO objects(obj_id, kind, label, norm, provenance) "
                "VALUES (?, ?, ?, ?, ?)",
                (obj_id, kind, canonical_label, norm, provenance),
            )
            connection.execute(
                "INSERT OR IGNORE INTO aliases(norm, obj_id) VALUES (?, ?)",
                (norm, obj_id),
            )
        return MemoryRef(obj_id, canonical_label, kind, label)

    def add_alias(self, obj_id: str, alias: str) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO aliases(norm, obj_id) VALUES (?, ?)",
                (normalize(alias), obj_id),
            )
