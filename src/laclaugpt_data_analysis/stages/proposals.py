"""Proposal schemas: what each model stage is allowed to return.

These are the *contracts* between a stage and the model. Keeping them in one
readable module matters for two reasons:

1. A researcher can see the complete vocabulary an analysis can produce — every
   signifier, demand, frontier, formation, imaginary — without tracing each
   stage's call site.
2. Provenance is separable: everything a model returns is a *proposal*
   (`review_status="PROVISIONAL"` downstream). Nothing in these schemas asserts
   a finding about the world; they describe what the model may claim.

`_CoerceStringListFields` exists because models frequently return a lone string
where the schema asks for a list. Coercing a single value into a one-element
list is a mechanical tolerance, not a loosening of the method: it never invents
content, it only accepts a differently-shaped rendering of the same answer.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from ..social_semiotic import MultimodalSummaryProposal

# Shortest quote that may count as verbatim evidence. Below this length a match
# is likely coincidence (a stray "AI" appears in almost any AI26 source), and a
# fragment masquerading as a substantiated quotation is worse than no evidence.
_MIN_QUOTE_CHARS = 12


class _CoerceStringListFields:
    """Accept a bare string where a `list[str]` field was declared."""

    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def _single_value_to_list(cls, value: Any, info: Any) -> Any:
        name = getattr(info, "field_name", "")
        model_fields = getattr(cls, "model_fields", {})
        declared = model_fields.get(name)
        if declared is None:
            return value
        annotation = str(declared.annotation)
        is_string_list = "list[str]" in annotation.replace(" ", "") or (
            "list" in annotation and "str" in annotation
        )
        if not is_string_list:
            return value
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return value


class FrameProposal(BaseModel):
    """Historical frame schema retained for EP24/generic reproducibility."""

    description: str = ""
    framing: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    visible_text: list[str] = Field(default_factory=list)
    usernames: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    rhetorical_cues: list[str] = Field(default_factory=list)
    candidate_signifiers: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


class EventCandidate(_CoerceStringListFields, BaseModel):
    description: str = ""
    time: str = ""
    location: str = ""
    actors: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)


class SummaryProposal(_CoerceStringListFields, BaseModel):
    """The descriptive first pass: what the item says, before theory."""

    summary: str = ""
    narrative: str = ""
    domain_classification: str = ""
    difficult_language: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    sentiment_observations: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    demands: list[str] = Field(default_factory=list)
    grievances: list[str] = Field(default_factory=list)
    event_candidates: list[EventCandidate] = Field(default_factory=list)
    candidate_signifiers: list[str] = Field(default_factory=list)
    candidate_articulations: list[str] = Field(default_factory=list)
    candidate_collective_subjects: list[str] = Field(default_factory=list)
    candidate_frontiers: list[str] = Field(default_factory=list)
    ai_definition_claims: list[str] = Field(default_factory=list)
    ai_capability_claims: list[str] = Field(default_factory=list)
    desirable_futures: list[str] = Field(default_factory=list)
    feared_futures: list[str] = Field(default_factory=list)
    sociotechnical_imaginary_candidates: list[str] = Field(default_factory=list)
    ownership_governance_assumptions: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


class DiscursiveElement(BaseModel):
    """One analytical element with the evidence that supports it.

    `confidence` and `uncertainty` are the model's own; the pipeline records them
    as proposals and never promotes them into findings.
    """

    label: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    uncertainty: str = ""


class DiscursiveRelation(BaseModel):
    """A directed relation between two elements (articulation, antagonism, ...)."""

    relation_type: str
    source: str
    target: str
    evidence: list[str] = Field(default_factory=list)


class DiscourseProposal(BaseModel):
    """Laclau/Mouffe analysis vocabulary, mirroring the theory the project tests.

    Field names follow the theory deliberately: demands, nodal points, floating
    and empty signifiers, frontiers, formations. A researcher should be able to
    read this class as the operationalisation of the framework.
    """

    demands: list[DiscursiveElement] = Field(default_factory=list)
    articulations: list[DiscursiveRelation] = Field(default_factory=list)
    equivalences: list[DiscursiveRelation] = Field(default_factory=list)
    differences: list[DiscursiveRelation] = Field(default_factory=list)
    antagonisms: list[DiscursiveRelation] = Field(default_factory=list)
    collective_subjects: list[DiscursiveElement] = Field(default_factory=list)
    frontiers: list[DiscursiveElement] = Field(default_factory=list)
    affects: list[DiscursiveElement] = Field(default_factory=list)
    nodal_point_candidates: list[DiscursiveElement] = Field(default_factory=list)
    floating_signifier_candidates: list[DiscursiveElement] = Field(default_factory=list)
    empty_signifier_candidates: list[DiscursiveElement] = Field(default_factory=list)
    formation_candidates: list[DiscursiveElement] = Field(default_factory=list)
    imaginary_candidates: list[DiscursiveElement] = Field(default_factory=list)
    populist: bool = False
    non_populist_reason: str = ""
    formula_of_populism: dict[str, Any] = Field(default_factory=dict)
    counter_evidence: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    abstentions: list[str] = Field(default_factory=list)


# What a summary stage may return. AI26 uses the multimodal proposal; the
# generic/EP24 path uses the plain summary. Both are accepted so one pipeline
# serves both corpora.
SummaryResult = SummaryProposal | MultimodalSummaryProposal

__all__ = [
    "DiscourseProposal",
    "DiscursiveElement",
    "DiscursiveRelation",
    "EventCandidate",
    "FrameProposal",
    "SummaryProposal",
    "SummaryResult",
    "_MIN_QUOTE_CHARS",
]
