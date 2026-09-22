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

import difflib
from typing import Any, Literal, get_args, get_origin

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

Mode = Literal[
    "linguistic", "visual", "auditory", "gestural", "spatial", "typographic",
    "symbolic_graphic", "temporal_editing", "interface_platform", "metadata", "other",
]
Confidence = Literal["high", "medium", "low", "unknown"]

# Similarity floor for absorbing a near-miss spelling of an enum value.  The
# closest pair of legitimate names in this module is
# ``typographic``/``symbolic_graphic`` at 0.667, while the spellings the model
# actually produced (``typography`` 0.857, ``lingustic`` 0.947, ``source__ref``
# 0.933) all sit above 0.85.  The floor therefore separates routine misspelling
# from a value the model genuinely did not choose.  Pinned by
# tests/test_issue_296_preanalysis_tolerance.py.
_NEAR_MISS_CUTOFF = 0.85

# Taxonomy members that mean "this does not classify the item".  Used when the
# model emits an explicit null for a Literal instead of one of the values.
_UNCLASSIFIED_MEMBERS = ("unknown", "other")


def _literal_options(annotation: Any) -> tuple[str, ...] | None:
    """Declared string options for a ``Literal[...]`` annotation, else None."""
    if get_origin(annotation) is Literal:
        options = get_args(annotation)
        if options and all(isinstance(option, str) for option in options):
            return tuple(options)
    return None


def _unclassified_member(options: tuple[str, ...]) -> str:
    for candidate in _UNCLASSIFIED_MEMBERS:
        if candidate in options:
            return candidate
    return options[-1]


def _closest_option(value: str, options: tuple[str, ...]) -> str | None:
    matches = difflib.get_close_matches(
        value, list(options), n=1, cutoff=_NEAR_MISS_CUTOFF
    )
    return matches[0] if matches else None


def _tolerate_literal(value: Any, annotation: Any) -> Any:
    """Absorb ``null`` and near-miss spellings for Literal-typed fields.

    Null list elements are dropped because they carry no information.  A null
    Literal becomes the taxonomy's own unclassified member.  A spelling that is
    not close to any option is returned untouched, so it still fails loudly
    instead of being silently mapped onto a category the model never chose.
    """
    if get_origin(annotation) is list:
        args = get_args(annotation)
        if len(args) != 1 or not isinstance(value, list):
            return value
        return [
            _tolerate_literal(item, args[0]) for item in value if item is not None
        ]
    options = _literal_options(annotation)
    if options is None:
        return value
    if value is None:
        return _unclassified_member(options)
    if isinstance(value, str) and value not in options:
        return _closest_option(value, options) or value
    return value


class StrictMethodModel(BaseModel):
    """Strict base for descriptive pre-analysis records.

    ``extra="forbid"`` stays: an unknown key still fails.  What is tolerated is
    routine *formatting* from the model, not analysis error.  Pre-analysis asks a
    local model to echo a seeded skeleton, so it predictably emits ``null`` for
    optional fields it has nothing to say about, and near-miss spellings of both
    keys and taxonomy values.  Rejecting those discards an otherwise usable
    record and burns a full model round trip (issues #100, #296).

    Tolerated: near-miss key spellings; ``null`` on an optional field (the
    default applies); ``null`` inside a list; ``null`` or a typo for a Literal.
    Still rejected: unknown keys, wrong types, missing required fields.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _tolerate_model_formatting(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        fields = cls.model_fields

        kept: dict[str, Any] = {}
        renamed: dict[str, Any] = {}
        for key, value in data.items():
            if key in fields:
                kept[key] = value
                continue
            alias = _closest_option(str(key), tuple(fields))
            if alias is not None and alias not in data:
                renamed[alias] = value
            else:
                # Keep it so extra="forbid" reports it rather than dropping it.
                kept[key] = value

        tolerated: dict[str, Any] = {}
        for key, value in {**kept, **renamed}.items():
            declared = fields.get(key)
            if declared is None:
                tolerated[key] = value
                continue
            normalised = _tolerate_literal(value, declared.annotation)
            if normalised is None and not declared.is_required():
                # An explicit null on an optional field means "not provided".
                continue
            tolerated[key] = normalised
        return tolerated


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
