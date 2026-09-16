"""Canonical statement/event models for optional Discourse Network Analysis.

These structures are derived analysis objects, not replacements for CanonicalRecord.
They preserve source identity, evidence, coding provenance, uncertainty and human
validation so network projections remain auditable.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ConceptType(StrEnum):
    POLICY_CLAIM = "policy_claim"
    FRAME = "frame"
    SIGNIFIER = "signifier"
    IMAGINARY = "imaginary"
    ISSUE_POSITION = "issue_position"
    CONCEPT = "concept"
    OTHER = "other"


class Stance(StrEnum):
    SUPPORT = "support"
    OPPOSE = "oppose"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ValidationStatus(StrEnum):
    PROVISIONAL = "provisional"
    VALIDATED = "validated"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class EvidenceSpan(BaseModel):
    quote: str = ""
    start_char: int | None = None
    end_char: int | None = None
    exact: bool = False

    @model_validator(mode="after")
    def validate_span(self) -> "EvidenceSpan":
        if (self.start_char is None) != (self.end_char is None):
            raise ValueError("start_char and end_char must be set together")
        if self.start_char is not None:
            if self.start_char < 0 or self.end_char is None or self.end_char <= self.start_char:
                raise ValueError("evidence offsets must define a positive span")
        return self


class DiscourseStatement(BaseModel):
    """One actor-concept coding event suitable for DNA/network projection."""

    statement_id: str
    source_url: str
    source_record_id: str | None = None
    actor_id: str
    actor_name: str
    concept_id: str
    concept_label: str
    concept_type: ConceptType = ConceptType.CONCEPT
    stance: Stance = Stance.UNKNOWN
    polarity: float | None = Field(default=None, ge=-1.0, le=1.0)
    relation_type: str | None = None
    timestamp: datetime | None = None
    evidence: EvidenceSpan = Field(default_factory=EvidenceSpan)
    collection_id: str | None = None
    coder_type: str = "unknown"
    coder_id_or_model: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    codebook_version: str | None = None
    validation_status: ValidationStatus = ValidationStatus.PROVISIONAL
    provenance: dict[str, Any] = Field(default_factory=dict)

    @property
    def signed_value(self) -> float:
        if self.polarity is not None:
            return self.polarity
        return {
            Stance.SUPPORT: 1.0,
            Stance.OPPOSE: -1.0,
            Stance.NEUTRAL: 0.0,
            Stance.MIXED: 0.0,
            Stance.UNKNOWN: 0.0,
        }[self.stance]
