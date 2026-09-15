"""Persistent memory/codebook models."""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

ReviewState = Literal["PROVISIONAL", "ACCEPTED", "REJECTED", "REVISED", "CANONICAL"]


def stable_id(namespace: str, label: str) -> str:
    digest = hashlib.sha256(f"{namespace}:{label.casefold().strip()}".encode()).hexdigest()[:16]
    return f"{namespace}_{digest}"


class MemoryEntry(BaseModel):
    entry_id: str
    namespace: str
    canonical_label: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    valid_from: str | None = None
    valid_to: str | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    review_state: ReviewState = "PROVISIONAL"

    @classmethod
    def create(cls, namespace: str, label: str, **kwargs):
        return cls(entry_id=stable_id(namespace, label), namespace=namespace,
                   canonical_label=label, **kwargs)


class Resolution(BaseModel):
    query: str
    entry_id: str | None = None
    score: float = 0.0
    candidates: list[str] = Field(default_factory=list)
    abstained: bool = False
