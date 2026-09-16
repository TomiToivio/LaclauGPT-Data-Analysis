"""Evidence-linked framing models for AI26 and other studies.

This module operationalizes a deliberately small subset of Entman-style framing and
collective-action framing.  It does not claim to operationalize all of Goffman, and it
keeps frame proposals separate from ideology or Laclaudian interpretation.
"""
from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .discourse_network.models import EvidenceSpan, ValidationStatus


class FrameKind(StrEnum):
    PROBLEM = "problem_definition"
    CAUSE = "causal_attribution"
    EVALUATION = "normative_evaluation"
    REMEDY = "remedy"
    DIAGNOSTIC = "diagnostic"
    PROGNOSTIC = "prognostic"
    MOTIVATIONAL = "motivational"


class FrameElement(BaseModel):
    kind: FrameKind
    text: str
    evidence: EvidenceSpan
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    coder_type: str = "unknown"
    coder_id_or_model: str | None = None
    validation_status: ValidationStatus = ValidationStatus.PROVISIONAL
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_grounded_text(self) -> "FrameElement":
        if self.text and not self.evidence.quote:
            raise ValueError("frame elements require an evidence quote")
        return self


class FrameProposal(BaseModel):
    frame_id: str
    statement_id: str
    source_record_id: str | None = None
    source_url: str
    label: str | None = None
    elements: list[FrameElement] = Field(default_factory=list)
    project_id: str | None = None
    arena: str | None = None
    platform: str | None = None
    reviewed_by: str | None = None
    review_note: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_elements(self) -> "FrameProposal":
        if not self.elements:
            raise ValueError("a frame proposal must contain at least one grounded element")
        return self


def frame_table(frames: list[FrameProposal]) -> list[dict[str, Any]]:
    """Flatten frames into a visualization-friendly evidence table."""
    rows: list[dict[str, Any]] = []
    for frame in frames:
        for element in frame.elements:
            rows.append(
                {
                    "frame_id": frame.frame_id,
                    "statement_id": frame.statement_id,
                    "source_record_id": frame.source_record_id,
                    "source_url": frame.source_url,
                    "label": frame.label,
                    "kind": element.kind.value,
                    "text": element.text,
                    "evidence_quote": element.evidence.quote,
                    "evidence_start": element.evidence.start_char,
                    "evidence_end": element.evidence.end_char,
                    "evidence_exact": element.evidence.exact,
                    "confidence": element.confidence,
                    "validation_status": element.validation_status.value,
                    "project_id": frame.project_id,
                    "arena": frame.arena,
                    "platform": frame.platform,
                    "coder_type": element.coder_type,
                    "coder_id_or_model": element.coder_id_or_model,
                }
            )
    return rows


def frame_frequency(frames: list[FrameProposal]) -> list[dict[str, Any]]:
    """Count frame-element kinds without treating frequency as resonance/effectiveness."""
    counts = Counter(element.kind.value for frame in frames for element in frame.elements)
    return [{"kind": kind, "count": count} for kind, count in sorted(counts.items())]
