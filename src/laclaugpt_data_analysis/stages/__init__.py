"""The Phase 1 analysis pipeline, one file per scientific step.

Read these in order to understand what LaclauGPT does to one post:

    shared.py       shared plumbing (context, prompt envelope, provenance)
    proposals.py    the schemas a model stage may return
    prompt_map.py   which prompt each stage uses
    preprocess.py   stage 1 — extract ASR/OCR/frames/translations
    frame.py        stage 2a — per-frame multimodal evidence analysis
    summary.py      stage 2b — descriptive first pass
    laclau.py       stage 3 — Laclau/Mouffe discourse analysis
    postprocess.py  stage 4 — write the canonical analysis record
    graph.py        stage 5 — project for export/dashboard
    evidence.py     evidence verification (the pipeline's integrity rule)
    runner.py       thin sequencing of the steps above

`runner.py` is the entry point; every other module is either a stage or the
infrastructure a stage needs.
"""
from __future__ import annotations

from .graph import build_discourse_graph
from .postprocess import postprocess_record
from .preprocess import preprocess_record
from .prompt_map import phase1_preanalysis_prompt_ids, prompt_ids_for_stage
from .proposals import (
    DiscourseProposal,
    DiscursiveElement,
    DiscursiveRelation,
    EventCandidate,
    FrameProposal,
    SummaryProposal,
    SummaryResult,
)
from .runner import evidence_ids, run_canonical_pipeline
from .shared import (
    GraphSink,
    PipelineContext,
    Preprocessor,
    VectorSink,
    analysis_flags,
    analysis_phase,
    append_stage,
    effective_stage_set,
    enabled,
    envelope_for_stage,
    memory_text,
    model_run_metadata,
    phase_allows,
    project_config_sha256,
    validate_project_analysis_config,
)

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
