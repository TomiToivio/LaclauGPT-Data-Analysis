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
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_alias_norm ON aliases(norm)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_object_kind_state "
                "ON objects(kind, state)"
            )

    @staticmethod
    def _validate_kind(kind: str) -> None:
        if kind not in KINDS:
            raise ValueError(f"unsupported memory kind: {kind}")

    def _resolve_states(self, raw: str, kind: str, states: tuple[str, ...]) -> Resolution:
        self._validate_kind(kind)
        norm = normalize(raw)
        if not norm:
            return Resolution(raw=raw, kind=kind, decision="NEW")
        placeholders = ",".join("?" for _ in states)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT DISTINCT o.obj_id, o.label FROM aliases a "
                "JOIN objects o ON o.obj_id = a.obj_id "
                "WHERE a.norm = ? AND o.kind = ? "
                f"AND o.state IN ({placeholders}) "
                "ORDER BY o.obj_id",
                (norm, kind, *states),
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
                score=0.0,
            )
        return Resolution(raw=raw, kind=kind, decision="NEW")

    def resolve(self, raw: str, kind: str) -> Resolution:
        """Resolve review-visible objects, abstaining on alias collisions."""
        return self._resolve_states(raw, kind, ("CANONICAL", "PROVISIONAL", "DEPRECATED"))

    def resolve_accepted(self, raw: str, kind: str) -> Resolution:
        """Resolve only researcher-accepted canonical objects.

        This is the only resolver intended for automatic runtime normalization.
        Provisional LLM/research suggestions remain visible for review but can
        never become accepted continuity identifiers without an explicit state
        transition.
        """
        return self._resolve_states(raw, kind, ("CANONICAL",))

    def create(
        self,
        obj_id: str,
        kind: str,
        label: str,
        provenance: str = "",
        *,
        state: str = "PROVISIONAL",
    ) -> MemoryRef:
        self._validate_kind(kind)
        if state not in STATES:
            raise ValueError(f"unsupported memory state: {state}")
        norm = normalize(label)
        if not norm:
            raise ValueError("memory label may not be empty")
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

    def propose(self, kind: str, label: str, *, provenance: str = "") -> MemoryRef:
        """Persist a deterministic PROVISIONAL object without accepting it."""
        obj_id = stable_memory_id(kind, label)
        try:
            return self.create(obj_id, kind, label, provenance=provenance)
        except sqlite3.IntegrityError:
            resolution = self.resolve(label, kind)
            if resolution.decision == "EXISTING" and resolution.obj_id == obj_id:
                return MemoryRef(obj_id, resolution.label, kind, label)
            raise

    def set_state(self, obj_id: str, state: str) -> None:
        """Explicit researcher/review transition; never called by resolve()."""
        if state not in STATES:
            raise ValueError(f"unsupported memory state: {state}")
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                "UPDATE objects SET state = ? WHERE obj_id = ?",
                (state, obj_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(obj_id)

    def accept(self, obj_id: str) -> None:
        """Mark an already-reviewed object canonical."""
        self.set_state(obj_id, "CANONICAL")

    def add_alias(self, obj_id: str, alias: str) -> None:
        norm = normalize(alias)
        if not norm:
            raise ValueError("memory alias may not be empty")
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
