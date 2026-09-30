"""Canonical staged LaclauGPT analysis orchestration — compatibility facade.

The pipeline itself now lives in `laclaugpt_data_analysis.stages`, one module per
scientific step. Read `stages/runner.py` first; it sequences the whole thing.

This module remains the import path that existing callers use, and re-exports
every public name that was previously defined here. It is a facade, not a second
implementation: the objects below ARE the stage objects, so there is exactly one
`PipelineContext` class and one `DiscourseProposal` in the process. Two classes
with the same name would not compare equal, which would break callers that pass a
context across the boundary.

New code should import from `laclaugpt_data_analysis.stages`.
"""
# ruff: noqa: F401  -- every import here is a deliberate re-export for callers
# that still import from this historic path. Removing one would break them.
from __future__ import annotations

# The multimodal proposal classes historically lived in this module. They are
# defined in `social_semiotic`; re-exported here so the historic import path works.
from .social_semiotic import (  # noqa: F401
    MultimodalFrameProposal,
    MultimodalSummaryProposal,
)

# Stage implementations and their schemas, re-exported for existing callers.
from .stages import (
    DiscourseProposal,
    DiscursiveElement,
    DiscursiveRelation,
    EventCandidate,
    FrameProposal,
    GraphSink,
    PipelineContext,
    Preprocessor,
    SummaryProposal,
    SummaryResult,
    VectorSink,
    analysis_flags,
    analysis_phase,
    append_stage,
    build_discourse_graph,
    effective_stage_set,
    enabled,
    envelope_for_stage,
    evidence_ids,
    memory_text,
    model_run_metadata,
    phase1_preanalysis_prompt_ids,
    phase_allows,
    postprocess_record,
    preprocess_record,
    project_config_sha256,
    prompt_ids_for_stage,
    run_canonical_pipeline,
    validate_project_analysis_config,
)
from .stages.evidence import evidence_ids as _evidence_ids
from .stages.evidence import locate_quote as _locate_quote
from .stages.frame import analyze_frames
from .stages.laclau import discourse_analysis
from .stages.postprocess import _objects, _relation_chains, _summary_uncertainty
from .stages.postprocess import postprocess_record as _postprocess_record
from .stages.preprocess import preprocess_record as _preprocess_record
from .stages.proposals import _MIN_QUOTE_CHARS  # noqa: F401  (historic constant)
from .stages.shared import _AI26_CAPABILITIES, _PHASE2_CAPABILITIES  # noqa: F401
from .stages.shared import validate_project_analysis_config as _validate_project_analysis_config
from .stages.summary import summarize_record

# Historic private aliases. Some tests and sibling modules reach for these
# underscore-prefixed names; they are kept pointing at the single implementation
# so behaviour cannot diverge.
_append_stage = append_stage
_effective_stage_set = effective_stage_set
_enabled = enabled

__all__ = [
    "DiscourseProposal",
    "DiscursiveElement",
    "DiscursiveRelation",
    "EventCandidate",
    "FrameProposal",
    "GraphSink",
    "PipelineContext",
    "Preprocessor",
    "SummaryProposal",
    "SummaryResult",
    "VectorSink",
    "analysis_flags",
    "analysis_phase",
    "append_stage",
    "build_discourse_graph",
    "effective_stage_set",
    "enabled",
    "envelope_for_stage",
    "evidence_ids",
    "memory_text",
    "model_run_metadata",
    "phase1_preanalysis_prompt_ids",
    "phase_allows",
    "postprocess_record",
    "preprocess_record",
    "project_config_sha256",
    "prompt_ids_for_stage",
    "run_canonical_pipeline",
    "validate_project_analysis_config",
]
