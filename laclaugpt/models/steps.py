"""Output models for the seven analysis steps.

One class per step, in step order, so the whole pipeline's data contract is
readable in one file. Each class mirrors what its step writes.

Legacy correspondence (steps 1-5):
    Step1PreprocessOutput  <- puhti_preprocess.py
    Step2FrameOutput       <- puhti_frame.py
    Step3SummaryOutput     <- puhti_summary.py
    Step4PostprocessOutput <- puhti_postprocess.py
    Step5DiscourseOutput   <- puhti_populism.py

Steps 6 and 7 have no legacy counterpart.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- 1. preprocess
class ExtractedFrame(BaseModel):
    """One sampled video frame written to disk."""

    frame_id: str
    timestamp_seconds: float = Field(ge=0)
    local_path: str
    # OCR text found in this frame. Empty is a valid result.
    ocr_text: str = ""


class Step1PreprocessOutput(BaseModel):
    """Media extraction: frames, OCR, transcript and translation.

    Legacy wrote six fixed ``ocr_1..ocr_6`` columns and a single
    ``whisper_transcript``. A list is used here instead, so the number of frames
    is not baked into the schema; the legacy columns are mappable onto it.
    """

    frames: list[ExtractedFrame] = Field(default_factory=list)
    transcript: str = ""
    transcript_language: str | None = None
    transcript_translated: str | None = None
    # True when nothing needed extracting (for example a text-only record).
    nothing_to_extract: bool = False


# ------------------------------------------------------------ 2. frame_analysis
class FrameReading(BaseModel):
    """One multimodal reading of one frame or image."""

    frame_id: str
    analysis: str = ""
    # Low-confidence or unusable frames abstain rather than guessing (INV_ABSTAIN).
    abstained: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: str | None = None


class Step2FrameOutput(BaseModel):
    """Visual readings of a record's images / sampled frames.

    Legacy wrote ``frame_analysis_1..6``. A list is used here for the same reason
    as in step 1.
    """

    readings: list[FrameReading] = Field(default_factory=list)
    # Set when the record had no images or frames at all.
    skipped_no_media: bool = False


# ------------------------------------------------------------------- 3. summary
class Step3SummaryOutput(BaseModel):
    """The multimodal summary of the whole record.

    Inputs are the source metadata, transcript and any frame readings, per the
    legacy ``puhti_summary.py`` prompt.
    """

    summary: str = ""
    abstained: bool = False
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------- 4. postprocess
class Sentiment(BaseModel):
    """Sentiment split, as in the legacy ``Sentiment`` model."""

    positive: list[str] = Field(default_factory=list)
    neutral: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)


class Step4PostprocessOutput(BaseModel):
    """Structured fields lifted out of the free-text summary.

    Descriptive only. Topics and entities are candidate structures, not
    discourse-theoretical claims (AGENTS.md methodological boundary).
    """

    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    sentiment: Sentiment = Field(default_factory=Sentiment)
    extra: dict[str, Any] = Field(default_factory=dict)


# ----------------------------------------------------------------- 5. discourse
class PopulismElement(BaseModel):
    """One element of the Us / Frontier construction, per Palonen.

    Mirrors the legacy ``PopulismElement`` model.
    """

    populism_element: str = ""
    populism_affect: str = ""


class Step5DiscourseOutput(BaseModel):
    """Laclaudian discourse analysis.

    Mirrors the legacy ``FormulaOfPopulism`` model. These are interpretation, not
    computation: every field is provisional and human-reviewable (INV_HUMAN_REVIEW),
    and ``populist`` may only be set from evidenced Us and Frontier construction
    (INV_POPULISM), never from sentiment or keyword frequency.
    """

    populism_analysis: str = ""
    populism_us: list[PopulismElement] = Field(default_factory=list)
    populism_frontier: list[PopulismElement] = Field(default_factory=list)

    # Optional Laclaudian signifier roles, kept separate from the populism
    # formula because they are distinct theoretical claims.
    signifiers: list[str] = Field(default_factory=list)
    nodal_points: list[str] = Field(default_factory=list)
    empty_signifier_candidates: list[str] = Field(default_factory=list)

    abstained: bool = False


# ----------------------------------------------------------------------- 6. dna
class DnaStatement(BaseModel):
    """One actor-concept statement in the Discourse Network Analysis sense.

    Field semantics follow the verified DNA model: ``agreement`` is genuinely
    binary (support / reject) and ``None`` means uncoded, which must stay missing
    rather than being coerced to support.
    """

    statement_id: str
    actor_id: str = ""
    actor_name: str = ""
    concept_id: str = ""
    concept_label: str = ""
    agreement: bool | None = None
    agreement_status: str = "abstain"
    evidence_text: str | None = None


class Step6DnaOutput(BaseModel):
    """Discourse Network Analysis statements extracted from the discourse result."""

    statements: list[DnaStatement] = Field(default_factory=list)
    abstained: bool = False


# ----------------------------------------------------------------------- 7. sna
class SnaNode(BaseModel):
    """One node in the social network."""

    node_id: str
    node_type: str = "unknown"
    label: str | None = None


class SnaEdge(BaseModel):
    """One edge, with an explicit communication mode.

    ``communication_mode`` records whether the interaction was human-generated,
    machine-generated or machine-mediated, so artificial communicators are
    representable rather than assumed absent.
    """

    edge_id: str
    source: str
    target: str
    relation_type: str = ""
    weight: float = 1.0
    communication_mode: str = "unknown"


class Step7SnaOutput(BaseModel):
    """Social Network Analysis over the DNA statements.

    Metrics here are conventional network-science measures. None of them is a
    theoretical construct: betweenness is not "network power", and no measure may
    be relabelled as a Castells concept.
    """

    nodes: list[SnaNode] = Field(default_factory=list)
    edges: list[SnaEdge] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    interpretation_boundary: str = (
        "conventional network-science measures; theoretical interpretation "
        "requires separate evidence and argument"
    )
