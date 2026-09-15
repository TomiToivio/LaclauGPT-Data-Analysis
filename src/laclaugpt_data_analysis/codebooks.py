"""Versioned machine-readable codebooks and safe memory seeding."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from .memory.models import KIND_PREFIX, KINDS


class CodebookEntry(BaseModel):
    kind: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    definition: str = ""
    provenance: str = ""


class Codebook(BaseModel):
    codebook_id: str
    version: str
    title: str
    description: str = ""
    entries: list[CodebookEntry] = Field(default_factory=list)


def stable_codebook_id(entry: CodebookEntry) -> str:
    if entry.kind not in KINDS:
        raise ValueError(f"unsupported memory kind: {entry.kind}")
    digest = hashlib.sha256(f"{entry.kind}:{entry.label.casefold().strip()}".encode()).hexdigest()[:12]
    return f"{KIND_PREFIX[entry.kind]}-{digest}"


def load_codebook(path: str | Path) -> Codebook:
    source = Path(path)
    if source.suffix.lower() != ".json":
        raise ValueError("machine-readable codebooks must use JSON")
    return Codebook.model_validate(json.loads(source.read_text(encoding="utf-8")))


def seed_memory(codebook: Codebook, store) -> list[str]:
    ids: list[str] = []
    for entry in codebook.entries:
        obj_id = stable_codebook_id(entry)
        existing = store.resolve(entry.label, entry.kind)
        if existing.decision != "EXISTING":
            store.create(obj_id, entry.kind, entry.label, provenance=entry.provenance)
        for alias in entry.aliases:
            store.add_alias(obj_id, alias)
        ids.append(obj_id)
    return ids
