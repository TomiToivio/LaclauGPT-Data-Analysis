"""Small Pydantic validation models for Phase 0."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


_LIST_FIELDS = (
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

    for field_name in _LIST_FIELDS:
        if field_name not in normalised:
            continue

        value = normalised[field_name]
        if isinstance(value, list):
            continue
        if value is None:
            normalised[field_name] = []
            coerced_fields.append(field_name)
            continue
        if isinstance(value, str):
            text = value.strip()
            normalised[field_name] = [text] if text else []
            coerced_fields.append(field_name)

    return normalised, coerced_fields


def validate_summary(record: dict[str, Any], summary: dict[str, Any]) -> DocumentSummary:
    metadata = record.get("metadata") or {}
    normalised, coerced_fields = _normalise_list_fields(summary)

    if coerced_fields:
        notes = list(normalised.get("uncertainty_notes") or [])
        fields = ", ".join(coerced_fields)
        notes.append(
            f"Phase 0 postprocess normalized scalar list field(s) to one-element lists: {fields}."
        )
        normalised["uncertainty_notes"] = notes

    payload = {
        **normalised,
        "document_id": record["document_id"],
        "source_url": metadata.get("source_url") or record.get("source_url") or "",
        "source_date": metadata.get("source_date"),
        "actor_name": metadata.get("actor_name"),
        "title": metadata.get("title"),
    }
    return DocumentSummary.model_validate(payload)
