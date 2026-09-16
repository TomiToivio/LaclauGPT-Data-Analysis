"""Canonical staged pipeline with stage-specific unified context assembly."""
from __future__ import annotations

from typing import Any

from .canonical import CanonicalRecord
from .canonical_pipeline import (
    GraphSink,
    Preprocessor,
    VectorSink,
    analyze_frames,
    build_discourse_graph,
    discourse_analysis,
    postprocess_record,
    preprocess_record,
    summarize_record,
)
from .codebooks import CodebookEntry
from .context_orchestration import AnalysisContextPolicy, assemble_analysis_context
from .context_runtime import ContextItem
from .periodic_summary import PeriodicSummaryRepository
from .rag import RetrievalBackend


def _append_context_audit(
    record: CanonicalRecord,
    stage: str,
    audit: dict[str, Any],
) -> None:
    key = f"analysis_context:{stage}"
    existing = record.intermediate.stage_outputs.get(key)
    history = existing if isinstance(existing, list) else ([] if existing is None else [existing])
    history.append(audit)
    record.intermediate.stage_outputs[key] = history


def run_contextual_canonical_pipeline(
    record: CanonicalRecord,
    *,
    provider,
    project_id: str,
    codebook_entries: list[CodebookEntry] | None = None,
    policy: AnalysisContextPolicy | None = None,
    summary_repository: PeriodicSummaryRepository | None = None,
    retrieval_backend: RetrievalBackend | None = None,
    memory_items: list[ContextItem] | None = None,
    preprocessor: Preprocessor | None = None,
    graph_sink: GraphSink | None = None,
    vector_sink: VectorSink | None = None,
    model: str = "auto",
    project_profile: str = "generic",
    prompt_version: str = "canonical-v1",
    allow_cloud_fallback: bool | None = None,
) -> CanonicalRecord:
    """Run the canonical ladder while assembling task-relevant context per LLM stage."""
    entries = codebook_entries or []
    active_policy = policy or AnalysisContextPolicy()
    record = preprocess_record(record, preprocessor=preprocessor)

    frame_bundle, frame_context = assemble_analysis_context(
        record,
        project_id=project_id,
        stage="frame",
        task="Versioned canonical frame-analysis task contract.",
        codebook_entries=entries,
        policy=active_policy,
        summary_repository=summary_repository,
        retrieval_backend=retrieval_backend,
        memory_items=memory_items,
    )
    _append_context_audit(record, "frame", frame_bundle.audit_snapshot())
    record = analyze_frames(
        record,
        provider=provider,
        context=frame_context,
        codebook_entries=entries,
        model=model,
        prompt_version=prompt_version,
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )

    summary_bundle, summary_context = assemble_analysis_context(
        record,
        project_id=project_id,
        stage="summary",
        task="Versioned canonical summary/pre-analysis task contract.",
        codebook_entries=entries,
        policy=active_policy,
        summary_repository=summary_repository,
        retrieval_backend=retrieval_backend,
        memory_items=memory_items,
    )
    _append_context_audit(record, "summary", summary_bundle.audit_snapshot())
    summary = summarize_record(
        record,
        provider=provider,
        context=summary_context,
        codebook_entries=entries,
        model=model,
        prompt_version=prompt_version,
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )

    discourse_bundle, discourse_context = assemble_analysis_context(
        record,
        project_id=project_id,
        stage="discourse",
        task="Versioned canonical discourse-analysis task contract.",
        codebook_entries=entries,
        policy=active_policy,
        summary_repository=summary_repository,
        retrieval_backend=retrieval_backend,
        memory_items=memory_items,
    )
    _append_context_audit(record, "discourse", discourse_bundle.audit_snapshot())
    discourse = discourse_analysis(
        record,
        provider=provider,
        context=discourse_context,
        codebook_entries=entries,
        model=model,
        prompt_version=prompt_version,
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )

    record = postprocess_record(record, summary, discourse)
    graph = build_discourse_graph(record)
    record.intermediate.stage_outputs.setdefault("discourse_graph", []).append(graph)
    if graph_sink is not None:
        graph_sink.write_graph(record.source_url, graph)
    if vector_sink is not None:
        vector_sink.upsert(
            record.source_url,
            record.human_readable.markdown or record.human_readable.summary or record.content.text,
            {
                "project_id": project_id,
                "source_url": record.source_url,
                "analysis_status": record.analysis.status,
            },
        )
    return record
