"""SQLite-backed stable-ID memory with deterministic alias resolution."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import (
    KINDS,
    STATES,
    MemoryRef,
    Resolution,
    display_label,
    normalize,
    stable_memory_id,
)


class SQLiteMemory:
    """Persistent analytical memory used only for continuity and normalization.

    Memory never constitutes source evidence. New model guesses should be stored
    as PROVISIONAL, and only explicit researcher action may mark them CANONICAL.
    """

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

    def _resolve(self, raw: str, kind: str, *, accepted_only: bool) -> Resolution:
        if kind not in KINDS:
            raise ValueError(f"unsupported memory kind: {kind}")
        norm = normalize(raw)
        if not norm:
            return Resolution(raw=raw, kind=kind, decision="NEW")

        state_clause = "AND o.state = 'CANONICAL'" if accepted_only else (
            "AND o.state NOT IN ('REJECTED', 'MERGED')"
        )
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT o.obj_id, o.label FROM aliases a "
                "JOIN objects o ON o.obj_id = a.obj_id "
                "WHERE a.norm = ? AND o.kind = ? "
                f"{state_clause} ORDER BY o.obj_id ASC",
                (norm, kind),
            ).fetchall()

        if len(rows) == 1:
            return Resolution(
                raw=raw,
                kind=kind,
                obj_id=rows[0][0],
                label=rows[0][1],
                decision="EXISTING",
                matched_via="alias",
                score=1.0,
            )
        if len(rows) > 1:
            return Resolution(
                raw=raw,
                kind=kind,
                decision="AMBIGUOUS",
                matched_via="alias",
                score=1.0,
            )
        return Resolution(raw=raw, kind=kind, decision="NEW")

    def resolve(self, raw: str, kind: str) -> Resolution:
        """Resolve against active memory, including provisional candidates."""
        return self._resolve(raw, kind, accepted_only=False)

    def resolve_accepted(self, raw: str, kind: str) -> Resolution:
        """Resolve only researcher-accepted canonical memory objects.

        This is the only resolver suitable for automatic output normalization:
        provisional objects remain reviewable but cannot silently become stable
        identifiers in Phase 1 analysis results.
        """
        return self._resolve(raw, kind, accepted_only=True)

    def create(
        self,
        obj_id: str,
        kind: str,
        label: str,
        provenance: str = "",
        *,
        state: str = "PROVISIONAL",
    ) -> MemoryRef:
        if kind not in KINDS:
            raise ValueError(f"unsupported memory kind: {kind}")
        if state not in STATES:
            raise ValueError(f"unsupported memory state: {state}")
        norm = normalize(label)
        if not norm:
            raise ValueError("memory label must not be empty")
        canonical_label = display_label(norm, kind)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO objects(obj_id, kind, label, norm, state, provenance) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (obj_id, kind, canonical_label, norm, state, provenance),
            )
            connection.execute(
                "INSERT OR IGNORE INTO aliases(norm, obj_id) VALUES (?, ?)",
                (norm, obj_id),
            )
        return MemoryRef(obj_id, canonical_label, kind, label)

    def create_stable(
        self,
        kind: str,
        label: str,
        provenance: str = "",
        *,
        state: str = "PROVISIONAL",
    ) -> MemoryRef:
        """Create one deterministic stable-ID object.

        The default remains PROVISIONAL. Callers must opt in explicitly to
        CANONICAL state for researcher-approved seeds.
        """
        return self.create(
            stable_memory_id(kind, label),
            kind,
            label,
            provenance=provenance,
            state=state,
        )

    def set_state(self, obj_id: str, state: str) -> None:
        """Explicitly change review state; CANONICAL promotion is reversible."""
        if state not in STATES:
            raise ValueError(f"unsupported memory state: {state}")
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                "UPDATE objects SET state = ? WHERE obj_id = ?",
                (state, obj_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(obj_id)

    def add_alias(self, obj_id: str, alias: str) -> None:
        norm = normalize(alias)
        if not norm:
            raise ValueError("memory alias must not be empty")
        with sqlite3.connect(self.path) as connection:
            exists = connection.execute(
                "SELECT 1 FROM objects WHERE obj_id = ?",
                (obj_id,),
            ).fetchone()
            if not exists:
                raise KeyError(obj_id)
            connection.execute(
                "INSERT OR IGNORE INTO aliases(norm, obj_id) VALUES (?, ?)",
                (norm, obj_id),
            )
