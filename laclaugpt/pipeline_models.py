"""Small, readable Pydantic contracts for the human-written Phase 2 pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MediaItem(BaseModel):
    """One image, video, audio file, or extracted frame attached to a record."""

    kind: str
    uri: str
    mime_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HumanPipelineRecord(BaseModel):
    """Minimal analysis view of a canonical record.

    source_url stays the canonical source identity. Extra canonical fields can be
    carried in metadata without making this hand-written layer own a replacement
    persistent schema.
    """

    source_url: str
    project: str
    source_text: str = ""
    language: str | None = None
    media: list[MediaItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FrameObservation(BaseModel):
    media_uri: str
    description: str
    evidence: list[str] = Field(default_factory=list)


class SummaryResult(BaseModel):
    summary: str
    evidence: list[str] = Field(default_factory=list)


class PostprocessResult(BaseModel):
    entities: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    affects: list[str] = Field(default_factory=list)


class LaclauResult(BaseModel):
    analysis: str
    us: list[str] = Field(default_factory=list)
    frontier: list[str] = Field(default_factory=list)
    demands: list[str] = Field(default_factory=list)
    affects: list[str] = Field(default_factory=list)
    empty_signifiers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class DNAResult(BaseModel):
    """Graph-ready discourse claims for a document/actor/concept network."""

    claims: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class SNAResult(BaseModel):
    """Graph-ready social relations derived from source evidence and metadata."""

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class AnalysisBundle(BaseModel):
    record: HumanPipelineRecord
    frames: list[FrameObservation] = Field(default_factory=list)
    summary: SummaryResult | None = None
    postprocess: PostprocessResult | None = None
    laclau: LaclauResult | None = None
    dna: DNAResult | None = None
    sna: SNAResult | None = None
