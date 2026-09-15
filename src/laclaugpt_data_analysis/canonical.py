"""Canonical cross-module LaclauGPT record used by Data Analysis.

Analysis enriches the Collection record without replacing source identity or deleting
raw/intermediate evidence. The four-layer contract preserves: exact raw capture,
intermediate stage outputs, current structured analysis and a human-readable researcher
summary. Legacy dataframe fields are deterministic projections of this record.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from .models import (
    ClassificationResult,
    EmbeddingResult,
    EntityMention,
    Model,
    Provenance,
    Representation,
    Topic,
    TopicAssignment,
)

SCHEMA_VERSION = "1.1.0"
ReviewStatus = Literal[
    "PROVISIONAL", "ACCEPTED", "REJECTED", "REVISED", "CANONICAL", "SUPERSEDED"
]


class RawCaptureSection(Model):
    ref: str | None = None
    payload: Any | None = None
    checksum: str | None = None
    content_type: str | None = None
    captured_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def preserved(self) -> bool:
        return bool(self.ref) or self.payload is not None


class IntermediateSection(Model):
    """Lossless stage outputs. Later stages append/replace named stage slots, not history."""

    asr: list[dict[str, Any]] = Field(default_factory=list)
    ocr: list[dict[str, Any]] = Field(default_factory=list)
    frames: list[dict[str, Any]] = Field(default_factory=list)
    frame_analysis: list[dict[str, Any]] = Field(default_factory=list)
    translations: list[dict[str, Any]] = Field(default_factory=list)
    stage_outputs: dict[str, Any] = Field(default_factory=dict)


class HumanReadableSection(Model):
    summary: str = ""
    markdown: str = ""
    generated_at: str | None = None
    generator: str = "laclaugpt-data-analysis"
    sections: dict[str, str] = Field(default_factory=dict)


class MediaReference(Model):
    kind: str = ""
    url: str = ""
    local_ref: str | None = None
    object_ref: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Transcript(Model):
    id: str
    text: str
    language: str | None = None
    translated_text: str | None = None
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, ge=0)
    provider: str | None = None
    provenance_id: str = ""


class OcrObservation(Model):
    id: str
    text: str
    frame_ref: str | None = None
    timestamp_seconds: float | None = Field(default=None, ge=0)
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance_id: str = ""


class FrameReference(Model):
    id: str
    timestamp_seconds: float = Field(ge=0)
    media_ref: str | None = None
    description: str | None = None
    provenance_id: str = ""


class SourceSection(Model):
    platform: str = ""
    source_type: str = ""
    author: str = ""
    author_fullname: str = ""
    created_at: datetime | None = None
    collected_at: datetime | None = None
    collector: str = ""
    collection_method: str = ""
    language: str = ""
    country: str = ""
    parent_source_url: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    raw_ref: str | None = None


class ContentSection(Model):
    text: str = ""
    title: str | None = None
    language: str | None = None
    translated_text: str | None = None
    transcripts: list[Transcript] = Field(default_factory=list)
    ocr: list[OcrObservation] = Field(default_factory=list)
    frames: list[FrameReference] = Field(default_factory=list)
    media_references: list[MediaReference] = Field(default_factory=list)
    file_references: list[str] = Field(default_factory=list)


class Evidence(Model):
    evidence_id: str
    kind: str
    source_url: str
    representation_id: str | None = None
    ref: str | None = None
    quote: str | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    timestamp_seconds: float | None = Field(default=None, ge=0)
    provenance_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Entity(Model):
    entity_id: str
    label: str
    entity_type: str | None = None
    aliases: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    provenance_id: str = ""
    review_status: ReviewStatus = "PROVISIONAL"


class DiscourseObject(Model):
    object_id: str
    label: str
    kind: str
    description: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    uncertainty: str | None = None
    provenance_id: str = ""
    review_status: ReviewStatus = "PROVISIONAL"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Relation(Model):
    relation_id: str
    relation_type: str
    source_ref: str
    target_ref: str
    evidence_ids: list[str] = Field(default_factory=list)
    provenance_id: str = ""
    review_status: ReviewStatus = "PROVISIONAL"


class AnalysisSection(Model):
    status: str = "collection-only"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: str | None = None
    representations: list[Representation] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    entity_mentions: list[EntityMention] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)
    topic_assignments: list[TopicAssignment] = Field(default_factory=list)
    classifications: list[ClassificationResult] = Field(default_factory=list)
    embeddings: list[EmbeddingResult] = Field(default_factory=list)
    formations: list[DiscourseObject] = Field(default_factory=list)
    signifiers: list[DiscourseObject] = Field(default_factory=list)
    nodal_points: list[DiscourseObject] = Field(default_factory=list)
    discourses: list[DiscourseObject] = Field(default_factory=list)
    imaginaries: list[DiscourseObject] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    us: list[DiscourseObject] = Field(default_factory=list)
    them: list[DiscourseObject] = Field(default_factory=list)
    frontier: list[DiscourseObject] = Field(default_factory=list)
    affects: list[DiscourseObject] = Field(default_factory=list)
    sentiments: list[DiscourseObject] = Field(default_factory=list)
    formula_of_populism: dict[str, Any] | None = None
    uncertainty: list[str] = Field(default_factory=list)
    abstentions: list[str] = Field(default_factory=list)
    codebook_refs: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    model_runs: list[dict[str, Any]] = Field(default_factory=list)


class ReviewSection(Model):
    status: ReviewStatus | None = None
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    note: str | None = None
    corrections: dict[str, Any] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    rerun_requests: list[str] = Field(default_factory=list)


class CanonicalRecord(Model):
    schema_version: str = SCHEMA_VERSION
    source_url: str
    source_native_ids: dict[str, str] = Field(default_factory=dict)
    raw_capture: RawCaptureSection = Field(default_factory=RawCaptureSection)
    source: SourceSection = Field(default_factory=SourceSection)
    content: ContentSection = Field(default_factory=ContentSection)
    intermediate: IntermediateSection = Field(default_factory=IntermediateSection)
    evidence: list[Evidence] = Field(default_factory=list)
    analysis: AnalysisSection = Field(default_factory=AnalysisSection)
    human_readable: HumanReadableSection = Field(default_factory=HumanReadableSection)
    provenance: list[Provenance] = Field(default_factory=list)
    review: ReviewSection = Field(default_factory=ReviewSection)
    legacy: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_url")
    @classmethod
    def require_source_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source_url is the canonical source identity and may not be empty")
        return value

    def canonical_dict(self) -> dict[str, Any]:
        """Reference JSON-compatible representation with UTC datetimes."""
        return self.model_dump(mode="json", exclude_none=False)

    def append_analysis_provenance(
        self,
        *,
        method: str,
        model: str | None = None,
        model_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Provenance:
        event = Provenance(
            method=method,
            model=model,
            model_version=model_version,
            created_at=datetime.now(UTC),
            metadata={"stage": "analysis", **(metadata or {})},
        )
        self.provenance.append(event)
        return event
