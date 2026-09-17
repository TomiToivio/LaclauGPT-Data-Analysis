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


class AgreementStatus(StrEnum):
    CODED = "coded"
    AMBIGUOUS = "ambiguous"
    NOT_APPLICABLE = "not_applicable"
    ABSTAIN = "abstain"


class ValidationStatus(StrEnum):
    PROVISIONAL = "provisional"
    REVIEWED = "reviewed"
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
    """One evidence-linked actor-concept claim suitable for several analysis methods.

    DNA-facing fields are explicit rather than inferred from Laclaudian relations.
    ``agreement`` means support/affirmation versus opposition/rejection of the coded
    concept only. ``None`` plus a non-coded ``agreement_status`` represents abstention
    or ambiguity and must be excluded from binary DNA projections until reviewed.
    """

    statement_id: str
    source_url: str
    source_record_id: str | None = None
    statement_type: str = "DNA Statement"
    actor_id: str
    actor_name: str
    person_id: str | None = None
    person_name: str | None = None
    organization_id: str | None = None
    organization_name: str | None = None
    target_actor_id: str | None = None
    target_actor_name: str | None = None
    concept_id: str
    concept_label: str
    original_concept_wording: str | None = None
    proposition: str | None = None
    concept_type: ConceptType = ConceptType.CONCEPT
    stance: Stance = Stance.UNKNOWN
    agreement: bool | None = None
    agreement_status: AgreementStatus = AgreementStatus.ABSTAIN
    polarity: float | None = Field(default=None, ge=-1.0, le=1.0)
    relation_type: str | None = None
    timestamp: datetime | None = None
    language: str | None = None
    evidence: EvidenceSpan = Field(default_factory=EvidenceSpan)
    collection_id: str | None = None
    project_id: str | None = None
    arena: str | None = None
    platform: str | None = None
    coder_type: str = "unknown"
    coder_id_or_model: str | None = None
    model_provider: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    codebook_version: str | None = None
    validation_status: ValidationStatus = ValidationStatus.PROVISIONAL
    abstained: bool = False
    abstention_reason: str | None = None
    duplicate_key: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    correction_note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_evidence_and_dna_semantics(self) -> "DiscourseStatement":
        if not (self.person_name or self.organization_name or self.actor_name):
            raise ValueError("DNA statement requires a person or organization actor")
        if self.agreement_status == AgreementStatus.CODED and self.agreement is None:
            raise ValueError("coded agreement_status requires agreement=true/false")
        if self.agreement is not None and self.agreement_status != AgreementStatus.CODED:
            raise ValueError("binary agreement requires agreement_status='coded'")
        if self.agreement is True and self.stance == Stance.UNKNOWN:
            self.stance = Stance.SUPPORT
        elif self.agreement is False and self.stance == Stance.UNKNOWN:
            self.stance = Stance.OPPOSE
        if self.stance == Stance.SUPPORT and self.agreement is None and not self.abstained:
            self.agreement = True
            self.agreement_status = AgreementStatus.CODED
        elif self.stance == Stance.OPPOSE and self.agreement is None and not self.abstained:
            self.agreement = False
            self.agreement_status = AgreementStatus.CODED
        if self.abstained:
            self.agreement = None
            if self.agreement_status == AgreementStatus.CODED:
                self.agreement_status = AgreementStatus.ABSTAIN
            return self
        if self.proposition and not self.evidence.quote:
            raise ValueError("non-abstained normalized claims with proposition require evidence")
        return self

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
