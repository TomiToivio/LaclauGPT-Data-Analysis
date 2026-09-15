"""Storage-neutral analytical contracts.

The public analysis package intentionally carries only the model fragments
required by analysis backends. Interpretive discourse claims remain separate
from descriptive NLP/topic/statistical outputs and should always retain
provenance and human-review context in downstream modules.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class Representation(Model):
    representation_id: str = Field(default_factory=lambda: _id("rep"))
    source_id: str
    representation_type: str = "text"
    text: str | None = None
    language: str | None = None
    provenance_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityMention(Model):
    mention_id: str = Field(default_factory=lambda: _id("mention"))
    representation_id: str
    surface_form: str
    spacy_label: str | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    candidate_entity_type: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class NlpDocument(Model):
    representation_id: str
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


class TopicAssignment(Model):
    target_id: str
    topic_id: str
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
    confidence: float | None = Field(default=None, ge=0, le=1)
    task: str = ""
    model: str = ""
    model_version: str = ""
    backend: str = ""
    provenance_id: str = ""
