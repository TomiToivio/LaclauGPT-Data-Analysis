"""Small Pydantic validation models for Phase 0."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    document_id: str
    source_url: str
    source_date: str | None = None
    actor_name: str | None = None
    title: str | None = None
    summary: str = ""
    claims: list[Any] = Field(default_factory=list)
    actors: list[Any] = Field(default_factory=list)
    entities: list[Any] = Field(default_factory=list)
    topics: list[Any] = Field(default_factory=list)
    signifiers: list[Any] = Field(default_factory=list)
    future_visions: list[Any] = Field(default_factory=list)
    governance_positions: list[Any] = Field(default_factory=list)
    evidence: list[Any] = Field(default_factory=list)
    uncertainty_notes: list[Any] = Field(default_factory=list)
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    prompt_version: str = ""


def validate_summary(record: dict[str, Any], summary: dict[str, Any]) -> DocumentSummary:
    metadata = record.get("metadata") or {}
    payload = {
        **summary,
        "document_id": record["document_id"],
        "source_url": metadata.get("source_url") or record.get("source_url") or "",
        "source_date": metadata.get("source_date"),
        "actor_name": metadata.get("actor_name"),
        "title": metadata.get("title"),
    }
    return DocumentSummary.model_validate(payload)
