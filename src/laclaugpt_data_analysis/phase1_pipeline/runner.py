"""Readable Phase 1 pipeline runner.

This file is intentionally boring. A researcher should be able to understand
the default analysis order by reading it from top to bottom:

    preprocess
    -> frame analysis when media exists
    -> descriptive summary
    -> Laclau discourse analysis
    -> postprocess
    -> optional persistence/export hooks

Infrastructure and scientific implementation details live behind those named
steps, not inside the orchestration itself.
"""
from __future__ import annotations

from datetime import UTC, datetime

from ..canonical import CanonicalRecord
from ..canonical_pipeline import (
    GraphSink,
    PipelineContext,
    Preprocessor,
    VectorSink,
    _append_stage,
    _enabled,
    _validate_project_analysis_config,
    build_discourse_graph,
)
from ..codebooks import CodebookEntry
from .frame import plan_modalities, run_frame_analysis
from .laclau import run_laclau_analysis
from .postprocess import run_postprocess
from .preprocess import run_preprocess
from .summary import run_summary


def run_phase1_pipeline(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext | None = None,
    codebook_entries: list[CodebookEntry] | None = None,
    preprocessor: Preprocessor | None = None,
    graph_sink: GraphSink | None = None,
    vector_sink: VectorSink | None = None,
    model: str = "auto",
    project_profile: str = "generic",
    prompt_version: str = "canonical-pipeline-v1",
    allow_cloud_fallback: bool | None = None,
) -> CanonicalRecord:
    """Run the complete human-readable Phase 1 analysis path for one record."""
    ctx = context or PipelineContext()
    if project_profile.casefold() == "ai26":
        _validate_project_analysis_config(ctx)

    entries = codebook_entries or []
    record.analysis.started_at = record.analysis.started_at or datetime.now(UTC)

    # 1. PREPROCESS: preserve the source and prepare derived text/media material.
    run_preprocess(record, preprocessor=preprocessor)

    # 2. FRAME: decide record-by-record whether visual analysis is possible.
    # Media present => multimodal processing. Text-only => cleanly skip vision.
    modality_plan = plan_modalities(record)
    run_frame_analysis(
        record,
        provider=provider,
        context=ctx,
        codebook_entries=entries,
        model=model,
        prompt_version=f"{prompt_version}:frame",
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
        plan=modality_plan,
    )

    # 3. SUMMARY: descriptive social-semiotic first pass over all available modes.
    summary = run_summary(
        record,
        provider=provider,
        context=ctx,
        codebook_entries=entries,
        model=model,
        prompt_version=f"{prompt_version}:summary",
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )

    # 4. LACLAU: discourse-theoretical interpretation remains a separate stage.
    discourse = run_laclau_analysis(
        record,
        provider=provider,
        context=ctx,
        codebook_entries=entries,
        model=model,
        prompt_version=f"{prompt_version}:discourse",
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )

    # 5. POSTPROCESS: canonical validation/projection plus legacy compatibility.
    run_postprocess(record, summary=summary, discourse=discourse, context=ctx)

    # Phase 2 / experimental methods remain explicit opt-ins after Phase 1.
    if _enabled(ctx, "critical_ai", default=False):
        from ..critical_ai import run_optional_critical_ai

        run_optional_critical_ai(
            record,
            provider=provider,
            context=ctx,
            codebook_entries=entries,
            model=model,
            allow_cloud_fallback=allow_cloud_fallback,
        )
    elif _enabled(ctx, "dna_statement_coding", default=False):
        from ..dna_statement_coding import run_optional_dna_statement_coding

        run_optional_dna_statement_coding(
            record,
            provider=provider,
            context=ctx,
            codebook_entries=entries,
            model=model,
            allow_cloud_fallback=allow_cloud_fallback,
        )

    # Persistence/export hooks are deliberately last. They do not alter the
    # scientific analysis, only where the validated result is made available.
    graph = build_discourse_graph(record)
    _append_stage(record, "discourse_graph", graph)
    if graph_sink:
        graph_sink.write_graph(record.source_url, graph)
    if vector_sink:
        vector_sink.upsert(
            record.source_url,
            record.human_readable.markdown or record.content.text,
            {"source_url": record.source_url, "project_profile": project_profile},
        )
    return record
