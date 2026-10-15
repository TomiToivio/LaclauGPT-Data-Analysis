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

import logging
from collections import deque
from difflib import SequenceMatcher
from typing import Literal, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Mode = Literal[
    "linguistic", "visual", "auditory", "gestural", "spatial", "typographic",
    "symbolic_graphic", "temporal_editing", "interface_platform", "metadata", "other",
]
Confidence = Literal["high", "medium", "low", "unknown"]

logger = logging.getLogger(__name__)

_LITERAL_SIMILARITY_FLOOR = 0.85

#: The catch-all member a taxonomy may declare for values it does not enumerate.
_CATCH_ALL_MEMBER = "other"

#: Which fields may fall back to the catch-all, and nothing else (issue #342).
#:
#: These are the observational taxonomies where the model demonstrably proposes a
#: *kind* the vocabulary does not list - observed live as ``methodology`` in
#: ``CriticalAIObject.types``, ``not_applicable`` in ``CriticalAIFinding.dimension`` and
#: a family of relation/process kinds in this module. A value that misses every member
#: is recorded as the taxonomy's own ``other``; the original string is kept in the
#: substitution ledger and the warning log, never discarded silently.
#:
#: Deliberately excluded: the ``Mode`` family, ``Confidence``, ``scope``, the finding and
#: review statuses, the DNA and config taxonomies, and everything else. Those stay
#: strict, because a wrong value there means the model misread the field rather than met
#: a kind the vocabulary lacks - ``modalities_present: ["zoological"]`` must keep failing.
_TAXONOMY_CATCH_ALL_FIELDS: dict[str, frozenset[str]] = {
    "ProcessObservation": frozenset({"process_type"}),
    "CircumstanceObservation": frozenset({"circumstance_type"}),
    "CompositionObservation": frozenset({"feature"}),
    "SignRelation": frozenset({"relation_type"}),
    "IntermodalRelation": frozenset({"relation_type"}),
    "UncertaintyObservation": frozenset({"category"}),
    "CriticalAIObject": frozenset({"types"}),
    "CriticalAIFinding": frozenset({"dimension"}),
}

_TAXONOMY_SUBSTITUTION_LIMIT = 200
_TAXONOMY_SUBSTITUTIONS: deque[dict[str, str]] = deque(maxlen=_TAXONOMY_SUBSTITUTION_LIMIT)


def taxonomy_catch_all_fields(model_name: str) -> frozenset[str]:
    """Return the catch-all-enabled fields declared for a model name."""
    return _TAXONOMY_CATCH_ALL_FIELDS.get(model_name, frozenset())


def _record_taxonomy_substitution(model_name: str, field_name: str, value: str) -> None:
    """Keep the value the vocabulary did not have, so drift stays auditable."""
    _TAXONOMY_SUBSTITUTIONS.append(
        {"model": model_name, "field": field_name, "value": value}
    )
    logger.warning(
        "taxonomy catch-all: %s.%s value %r is not a member; recorded as %r",
        model_name,
        field_name,
        value,
        _CATCH_ALL_MEMBER,
    )


def drain_taxonomy_substitutions() -> list[dict[str, str]]:
    """Return and clear the recorded substitutions.

    The pipeline may attach these to run provenance; the schemas themselves stay closed,
    because adding a durable per-record field is a contract decision, not an agent's.
    """
    drained = list(_TAXONOMY_SUBSTITUTIONS)
    _TAXONOMY_SUBSTITUTIONS.clear()
    return drained


def _has_negation_prefix_mismatch(value: str, member: str) -> bool:
    """Reject close spellings that reverse a taxonomy value's meaning."""
    value_folded = value.casefold()
    member_folded = member.casefold()
    for prefix in ("un", "in", "im", "ir", "il", "non", "dis", "de"):
        if value_folded == f"{prefix}{member_folded}":
            return True
        if member_folded == f"{prefix}{value_folded}":
            return True
    return False


def _normalise_literal_member(
    value,
    members: tuple[str, ...],
    *,
    catch_all: bool = False,
    model_name: str = "",
    field_name: str = "",
):
    """Normalise spelling drift, and fall back to the declared catch-all.

    A value that is plainly not a member is not guessed: when the field opts in
    via ``_TAXONOMY_CATCH_ALL_FIELDS`` the taxonomy's own ``other`` member is used
    and the original value is recorded. Otherwise the value is passed through
    unchanged, so Pydantic raises exactly as it did before.
    """
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
        if catch_all and _CATCH_ALL_MEMBER in members:
            _record_taxonomy_substitution(model_name, field_name, value)
            return _CATCH_ALL_MEMBER
        return value

    best_score = ranked[0][0]
    best = [member for score, member in ranked if score == best_score]
    if len(best) != 1:
        return value

    candidate = best[0]
    if _has_negation_prefix_mismatch(value, candidate):
        return value
    return candidate


def _normalise_literal_field(
    annotation,
    value,
    *,
    catch_all: bool = False,
    model_name: str = "",
    field_name: str = "",
):
    """Apply narrow tolerance to direct Literal fields and lists of Literals."""
    if get_origin(annotation) is Literal:
        members = tuple(member for member in get_args(annotation) if isinstance(member, str))
        return _normalise_literal_member(
            value, members, catch_all=catch_all, model_name=model_name, field_name=field_name
        )

    if get_origin(annotation) is list:
        args = get_args(annotation)
        if len(args) == 1 and get_origin(args[0]) is Literal and isinstance(value, list):
            members = tuple(
                member for member in get_args(args[0]) if isinstance(member, str)
            )
            return [
                _normalise_literal_member(
                    item,
                    members,
                    catch_all=catch_all,
                    model_name=model_name,
                    field_name=field_name,
                )
                for item in value
                if item is not None
            ]

    return value


def _normalise_taxonomy_payload(cls, value):
    """Tolerate null/unambiguous spelling drift without weakening strict schemas."""
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    catch_all_fields = taxonomy_catch_all_fields(cls.__name__)
    for field_name, field in cls.model_fields.items():
        if field_name in normalized:
            normalized[field_name] = _normalise_literal_field(
                field.annotation,
                normalized[field_name],
                catch_all=field_name in catch_all_fields,
                model_name=cls.__name__,
                field_name=field_name,
            )
    return normalized


class TaxonomyToleranceMixin(BaseModel):
    """Canonicalise unambiguous model drift in closed taxonomies (#299 rule).

    Near-miss spellings are canonicalised as before. Separately, a value that is not a
    member at all becomes the taxonomy's own ``other`` when the field is declared in
    :data:`_TAXONOMY_CATCH_ALL_FIELDS`; the original value is recorded in the
    substitution ledger and logged (#342).

    The tolerance is a property of the taxonomy contract, not of whichever base
    class a module happened to pick: every LLM-output schema that declares a
    ``Literal`` taxonomy should inherit this mixin so a value one step from
    exactly one canonical member is canonicalised identically everywhere.
    Unknown extra fields keep whatever ``extra`` policy the concrete model sets.
    """

    @model_validator(mode="before")
    @classmethod
    def _normalise_taxonomy_formatting(cls, value):
        return _normalise_taxonomy_payload(cls, value)


class StrictMethodModel(TaxonomyToleranceMixin):
    model_config = ConfigDict(extra="forbid")


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
