"""Public/private codebook loading and validation."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .memory.models import MemoryEntry


class Codebook(BaseModel):
    codebook_id: str
    version: str
    title: str
    description: str = ""
    entries: list[MemoryEntry] = Field(default_factory=list)


def load_codebook(path: str | Path) -> Codebook:
    source = Path(path)
    if source.suffix.lower() != ".json":
        raise ValueError("machine-readable codebooks must use JSON; Markdown remains documentation")
    return Codebook.model_validate(json.loads(source.read_text(encoding="utf-8")))


def dump_codebook(codebook: Codebook, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(codebook.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def seed_memory(codebook: Codebook, store) -> None:
    for entry in codebook.entries:
        store.put(entry)
