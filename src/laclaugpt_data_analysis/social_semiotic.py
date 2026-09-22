"""Method contract for descriptive multimodal social-semiotic pre-analysis.

This stage stops before discourse, ideology, sentiment, partisan, or populism
classification. It turns heterogeneous source material into an evidence-preserving
description for later LLM Structuralism and Laclau analysis.

Method lineage: Halliday/SFL; Kress and van Leeuwen multimodal social semiotics;
Martinec and Salway intersemiosis; and Wanselin, Danielsson and Wikman (2022).
Video/audio/platform support is an explicit LaclauGPT extension of a framework
demonstrated on static educational texts and therefore requires validation.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Literal, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Mode = Literal[
    "linguistic", "visual", "auditory", "gestural", "spatial", "typographic",
    "symbolic_graphic", "temporal_editing", "interface_platform", "metadata", "other",
]
Confidence = Literal["high", "medium", "low", "unknown"]

_LITERAL_SIMILARITY_FLOOR = 0.85


def _normalise_literal_member(value, members: tuple[str, ...]):
    """Normalise only unambiguous model-formatting drift for a closed taxonomy."""
    if value is None:
        for fallback in ("other", "unknown"):
            if fallback in members:
                return fallback
        return value
    if not isinstance(value, str) or value in members:
        return value

    folded = value.casefold()
    ranked = sorted(
        (
            (SequenceMatcher(None, folded, member.casefold()).ratio(), member)
            for member in members
        ),
        reverse=True,
    )
    if not ranked or ranked[0][0] < _LITERAL_SIMILARITY_FLOOR:
        return value

    best_score = ranked[0][0]
    best = [member for score, member in ranked if score == best_score]
    return best[0] if len(best) == 1 else value


def _normalise_literal_field(annotation, value):
    """Apply narrow tolerance to direct Literal fields and lists of Literals."""
    if get_origin(annotation) is Literal:
        members = tuple(member for member in get_args(annotation) if isinstance(member, str))
        return _normalise_literal_member(value, members)

    if get_origin(annotation) is list:
        args = get_args(annotation)
        if len(args) == 1 and get_origin(args[0]) is Literal and isinstance(value, list):
            members = tuple(
                member for member in get_args(args[0]) if isinstance(member, str)
            )
            return [
                _normalise_literal_member(item, members)
                for item in value
                if item is not None
            ]

    return value


class StrictMethodModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _normalise_taxonomy_formatting(cls, value):
        """Tolerate null/unambiguous spelling drift without weakening strict schemas."""
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        for field_name, field in cls.model_fields.items():
            if field_name in normalized:
                normalized[field_name] = _normalise_literal_field(
                    field.annotation,
                    normalized[field_name],
                )
        return normalized


class EvidencePointer(StrictMethodModel):
    evidence_id: str
    modality: Mode
    source_ref: str = ""
    exact_text: str = ""
    frame_id: str = ""
    timestamp_start: float | None = Field(default=None, ge=0)
    timestamp_end: float | None = Field(default=None, ge=0)
    confidence: Confidence = "unknown"
    uncertainty: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalise_model_emitted_pointer_fields(cls, value):
        """Tolerate narrow, known formatting drift in model-emitted evidence pointers.

        The pre-analysis contract remains strict for unknown fields. Only the
        observed source__ref near-miss is canonicalised, and optional text
        pointer fields accept explicit JSON null as equivalent to omission.
        """
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "source__ref" in normalized:
            if not normalized.get("source_ref"):
                normalized["source_ref"] = normalized["source__ref"]
            normalized.pop("source__ref", None)
        for field_name in ("source_ref", "exact_text", "frame_id", "uncertainty"):
            if normalized.get(field_name) is None:
                normalized[field_name] = ""
        return normalized


class EventCandidate(StrictMethodModel):
    """Descriptive event candidate retained for canonical compatibility."""

    description: str = ""
    time: str = ""
    location: str = ""
    actors: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)

    @field_validator("actors", "evidence", mode="before")
    @classmethod
    def _coerce_single_string(cls, value):
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return value


class SemioticResource(StrictMethodModel):
    mode: Mode
    description: str
    affordance_observed: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "unknown"


class ParticipantObservation(StrictMethodModel):
    participant_id: str
    description: str
    participant_type: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "unknown"


class ProcessObservation(StrictMethodModel):
    process_id: str
    description: str
    process_type: Literal[
        "material", "mental", "verbal", "relational", "behavioural",
        "existential", "visual_vector", "other",
    ] = "other"
    participant_refs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "unknown"


class CircumstanceObservation(StrictMethodModel):
    circumstance_id: str
    description: str
    circumstance_type: Literal[
        "time", "place", "manner", "cause", "accompaniment", "role", "angle", "other",
    ] = "other"
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "unknown"


class CompositionObservation(StrictMethodModel):
    feature: Literal[
        "layout", "salience", "foreground_background", "centre_periphery",
        "size_scale", "vector", "reading_viewing_order", "temporal_sequence",
        "repetition", "emphasis", "editing_transition", "sound_emphasis",
        "typography", "interface_placement", "other",
    ]
    description: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "unknown"


class SignObservation(StrictMethodModel):
    sign_id: str
    source_form: str
    description: str = ""
    modes: list[Mode] = Field(default_factory=list)
    salience_basis: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "unknown"


class SignRelation(StrictMethodModel):
    relation_type: Literal[
        "contrast", "opposition", "pairing", "repetition", "cooccurrence",
        "sequence", "label", "part_whole", "spatial_proximity", "other",
    ]
    source_sign_ref: str
    target_sign_ref: str
    description: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "unknown"


class IntermodalRelation(StrictMethodModel):
    relation_type: Literal[
        "redundancy", "repetition", "extension", "complementarity",
        "elaboration", "anchoring", "contrast", "conflict", "ambiguity", "other",
    ]
    modes: list[Mode]
    description: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "unknown"


class ConnotationObservation(StrictMethodModel):
    description: str
    basis: str
    alternatives: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "low"


class UncertaintyObservation(StrictMethodModel):
    category: Literal[
        "ocr", "asr", "translation", "visual", "audio", "speaker", "temporal",
        "missing_modality", "source_context", "model", "other",
    ]
    description: str
    affected_evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "unknown"


class MultimodalFrameProposal(StrictMethodModel):
    """Frame-level descriptive observation; frame never means political framing."""

    schema_version: str = "social-semiotic-preanalysis.v1"
    prompt_version: str = "v2"
    evidence: list[EvidencePointer] = Field(default_factory=list)
    denotation: list[str] = Field(default_factory=list)
    semiotic_resources: list[SemioticResource] = Field(default_factory=list)
    participants: list[ParticipantObservation] = Field(default_factory=list)
    processes: list[ProcessObservation] = Field(default_factory=list)
    circumstances: list[CircumstanceObservation] = Field(default_factory=list)
    composition: list[CompositionObservation] = Field(default_factory=list)
    salient_signs: list[SignObservation] = Field(default_factory=list)
    uncertainty: list[UncertaintyObservation] = Field(default_factory=list)

    # Descriptive compatibility projection for existing renderers.
    material_canvas_organisation: list[str] = Field(default_factory=list)
    scene_and_participants: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    visual_composition: list[str] = Field(default_factory=list)
    visible_text: list[str] = Field(default_factory=list)
    usernames: list[str] = Field(default_factory=list)
    symbols_and_interface_cues: list[str] = Field(default_factory=list)
    provenance_and_usage_cues: list[str] = Field(default_factory=list)
    semiotic_contribution: str = ""


class MultimodalSummaryProposal(StrictMethodModel):
    """Item-level, modality-agnostic social-semiotic pre-analysis."""

    schema_version: str = "social-semiotic-preanalysis.v1"
    prompt_version: str = "v2"
    summary: str = ""
    denotative_description: list[str] = Field(default_factory=list)
    source_languages: list[str] = Field(default_factory=list)
    modalities_present: list[Mode] = Field(default_factory=list)
    modalities_missing: list[Mode] = Field(default_factory=list)
    evidence: list[EvidencePointer] = Field(default_factory=list)
    semiotic_resources: list[SemioticResource] = Field(default_factory=list)
    participants: list[ParticipantObservation] = Field(default_factory=list)
    processes: list[ProcessObservation] = Field(default_factory=list)
    circumstances: list[CircumstanceObservation] = Field(default_factory=list)
    composition: list[CompositionObservation] = Field(default_factory=list)
    salient_signs: list[SignObservation] = Field(default_factory=list)
    sign_relations: list[SignRelation] = Field(default_factory=list)
    intermodal_relations: list[IntermodalRelation] = Field(default_factory=list)
    cautious_connotations: list[ConnotationObservation] = Field(default_factory=list)
    cross_modal_synthesis: str = ""
    uncertainty: list[UncertaintyObservation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    # Neutral compatibility projections.
    narrative: str = ""
    semiotic_modes: list[str] = Field(default_factory=list)
    cross_modal_relations: list[str] = Field(default_factory=list)
    difficult_language: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    event_candidates: list[EventCandidate] = Field(default_factory=list)

    @field_validator(
        "source_languages",
        "semiotic_modes",
        "cross_modal_relations",
        "difficult_language",
        "topics",
        "entities",
        "claims",
        "limitations",
        mode="before",
    )
    @classmethod
    def _coerce_single_string_list(cls, value):
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return value

    @property
    def sentiment_observations(self) -> list[str]:
        return []


PROHIBITED_PREANALYSIS_KEYS = frozenset({
    "empty_signifiers", "floating_signifiers", "nodal_points",
    "chains_of_equivalence", "chains_of_difference", "antagonisms", "frontiers",
    "populism", "ideology", "ideological_formation", "party_alignment",
    "political_alignment", "hegemony", "political_subjects", "political_demands",
    "sentiment", "sentiment_observations",
})


def assert_preanalysis_boundary(payload: dict) -> None:
    """Fail closed if a caller tries to persist downstream classifications."""
    stack: list[object] = [payload]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, child in value.items():
                if key.casefold() in PROHIBITED_PREANALYSIS_KEYS:
                    raise ValueError(
                        f"downstream analytical field is not allowed in pre-analysis: {key}"
                    )
                stack.append(child)
        elif isinstance(value, list):
            stack.extend(value)
