"""Typed multimodal evidence models with explicit provenance."""
from __future__ import annotations

from typing import Any

from pydantic import Field

from ..models import Model, Provenance


class TranscriptSegment(Model):
    segment_id: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance_id: str = ""


class OcrObservation(Model):
    observation_id: str
    frame_id: str
    timestamp_seconds: float = Field(ge=0)
    text: str
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance_id: str = ""


class VisualObservation(Model):
    observation_id: str
    frame_id: str
    timestamp_seconds: float = Field(ge=0)
    description: str
    categories: dict[str, list[str] | str] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance_id: str = ""


class MultimodalEvidenceBundle(Model):
    document_id: str
    source_uri: str | None = None
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    ocr: list[OcrObservation] = Field(default_factory=list)
    visuals: list[VisualObservation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: list[Provenance] = Field(default_factory=list)
    missing_modalities: list[str] = Field(default_factory=list)

    @property
    def has_evidence(self) -> bool:
        return bool(self.transcript or self.ocr or self.visuals or self.metadata)
