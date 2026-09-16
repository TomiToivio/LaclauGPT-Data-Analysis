"""Storage-neutral analytical contracts.

Derived analysis objects may have their own IDs, but `source_url` remains the
cross-module identity anchor whenever an object is persisted independently.
When objects are nested inside CanonicalRecord the enclosing record supplies the
same identity path.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(Model):
    provenance_id: str = Field(default_factory=lambda: _id("prov"))
    method: str
    model: str | None = None
    model_version: str | None = None
    pipeline_version: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at", mode="before")
    @classmethod
    def default_missing_legacy_timestamp(cls, value: Any) -> Any:
        """Treat explicit null/blank legacy timestamps like an omitted timestamp."""
        return datetime.now(UTC) if value in (None, "") else value


class Representation(Model):
    representation_id: str = Field(default_factory=lambda: _id("rep"))
    source_id: str
    source_url: str = ""
    representation_type: str = "text"
    text: str | None = None
    language: str | None = None
    provenance_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityMention(Model):
    mention_id: str = Field(default_factory=lambda: _id("mention"))
    representation_id: str
    source_url: str = ""
    surface_form: str
    spacy_label: str | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    candidate_entity_type: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class NlpDocument(Model):
    representation_id: str
    source_url: str = ""
    tokens: list[str] = Field(default_factory=list)
    sentences: list[str] = Field(default_factory=list)
    lemmas: list[str] = Field(default_factory=list)
    pos: list[str] = Field(default_factory=list)
    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    mentions: list[EntityMention] = Field(default_factory=list)
    language: str | None = None
    backend: str = ""
    model: str = ""
    provenance_id: str = ""


class EmbeddingResult(Model):
    item_id: str
    source_url: str = ""
    vector: list[float]
    model: str
    model_version: str = ""
    backend: str = ""
    dimensions: int = 0


class Topic(Model):
    topic_id: str = Field(default_factory=lambda: _id("topic"))
    canonical_label: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def label(self) -> str:
        """Stable display label used by graph/vector projections."""
        return self.canonical_label


class TopicAssignment(Model):
    target_id: str
    topic_id: str
    source_url: str = ""
    score: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance_id: str = ""
    review_status: str = "model_proposed"


class TopicModelResult(Model):
    topics: list[Topic] = Field(default_factory=list)
    assignments: list[TopicAssignment] = Field(default_factory=list)
    method: str = ""
    model_info: dict[str, Any] = Field(default_factory=dict)
    provenance_id: str = ""


class ClassificationResult(Model):
    label: str
    source_url: str = ""
    confidence: float | None = Field(default=None, ge=0, le=1)
    task: str = ""
    model: str = ""
    model_version: str = ""
    backend: str = ""
    provenance_id: str = ""
