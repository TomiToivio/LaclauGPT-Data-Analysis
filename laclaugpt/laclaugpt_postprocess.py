"""Small Pydantic validation models for Phase 0."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


LIST_FIELDS = (
    "claims",
    "actors",
    "entities",
    "topics",
    "signifiers",
    "future_visions",
    "governance_positions",
    "evidence",
    "uncertainty_notes",
)


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


def _normalise_list_fields(summary: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalised = dict(summary)
    coerced_fields: list[str] = []
    for field in LIST_FIELDS:
        value = normalised.get(field)
        if value is not None and not isinstance(value, list):
            normalised[field] = [value]
            coerced_fields.append(field)
    return normalised, coerced_fields


def validate_summary(record: dict[str, Any], summary: dict[str, Any]) -> DocumentSummary:
    metadata = record.get("metadata") or {}
    normalised_summary, coerced_fields = _normalise_list_fields(summary)
    if coerced_fields:
        notes = list(normalised_summary.get("uncertainty_notes") or [])
        notes.append(
            "Phase 0 postprocess normalised scalar values to one-element lists for: "
            + ", ".join(coerced_fields)
            + "."
        )
        normalised_summary["uncertainty_notes"] = notes

    payload = {
        **normalised_summary,
        "document_id": record["document_id"],
        "source_url": metadata.get("source_url") or record.get("source_url") or "",
        "source_date": metadata.get("source_date"),
        "actor_name": metadata.get("actor_name"),
        "title": metadata.get("title"),
    }
    return DocumentSummary.model_validate(payload)
