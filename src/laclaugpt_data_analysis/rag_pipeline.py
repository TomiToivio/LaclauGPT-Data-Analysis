"""RAG-aware orchestration over the canonical pipeline stages.

Retrieval is intentionally used for synthesis/discourse stages, not deterministic
preprocessing or frame-level source description. Retrieved material is context, never
source evidence. Any retrieval/index failure is recorded and ordinary analysis proceeds.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .canonical import CanonicalRecord
from .canonical_pipeline import (
    GraphSink,
    PipelineContext,
    Preprocessor,
    VectorSink,
    _append_stage,
    analyze_frames,
    build_discourse_graph,
    discourse_analysis,
    postprocess_record,
    preprocess_record,
    summarize_record,
)
from .codebooks import CodebookEntry
from .rag import RetrievalBackend, failed_context, record_filters


def _context_with_rag(base: PipelineContext, rendered: str, audit: dict[str, Any]) -> PipelineContext:
    provenance = {key: list(values) for key, values in base.provenance.items()}
    request_id = str(audit.get("request_id") or "")
    selected = [str(value) for value in audit.get("selected_canonical_ids") or []]
    if request_id:
        provenance.setdefault("rag_request_id", []).append(request_id)
    if selected:
        provenance.setdefault("rag_canonical_ids", []).extend(selected)
    provenance.setdefault("rag_method", []).append(str(audit.get("method") or "none"))
    return base.model_copy(update={"rag_context": rendered, "provenance": provenance})


def run_rag_pipeline(
    record: CanonicalRecord,
    *,
    provider,
    rag_backend: RetrievalBackend | None,
    rag_mode: str = "hybrid",
    rag_top_k: int = 20,
    rag_graph_depth: int = 2,
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
    """Run canonical analysis with bounded RAG for summary/discourse synthesis.

    RAG is deliberately absent from preprocessing and frame description. A failure in
    retrieval or indexing creates an auditable stage record and does not corrupt or abort
    canonical analysis.
    """
    base_context = context or PipelineContext()
    entries = codebook_entries or []
    record.analysis.started_at = record.analysis.started_at or datetime.now(UTC)

    preprocess_record(record, preprocessor=preprocessor)
    analyze_frames(
        record,
        provider=provider,
        context=base_context,
        codebook_entries=entries,
        model=model,
        prompt_version=f"{prompt_version}:frame",
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )

    synthesis_context = base_context
    if rag_backend is not None and rag_mode.casefold() != "none":
        filters = record_filters(record, dataset=project_profile)
        # Never retrieve the current source as its own memory item.
        filters.pop("source", None)
        query = (record.content.translated_text or record.content.text or record.content.title or "").strip()
        if query:
            try:
                retrieved = rag_backend.retrieve_context(
                    query,
                    filters,
                    top_k=rag_top_k,
                    depth=rag_graph_depth,
                    mode=rag_mode,
                )
            except Exception as exc:  # RAG is optional by contract
                embedding_model = str(getattr(rag_backend, "embedding_model", "") or "")
                retrieved = failed_context(
                    method=rag_mode,
                    filters=filters,
                    embedding_model=embedding_model,
                    error=exc,
                )
            audit = retrieved.audit.to_dict()
            rendered = retrieved.render()
            synthesis_context = _context_with_rag(base_context, rendered, audit)
            _append_stage(record, "rag_retrieval", audit)

    summary = summarize_record(
        record,
        provider=provider,
        context=synthesis_context,
        codebook_entries=entries,
        model=model,
        prompt_version=f"{prompt_version}:summary",
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )
    discourse = discourse_analysis(
        record,
        provider=provider,
        context=synthesis_context,
        codebook_entries=entries,
        model=model,
        prompt_version=f"{prompt_version}:discourse",
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )
    postprocess_record(record, summary, discourse)

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

    if rag_backend is not None:
        try:
            indexed = rag_backend.index_records([record])
            _append_stage(
                record,
                "rag_index",
                {
                    "status": "ok",
                    "indexed": indexed,
                    "source_url": record.source_url,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        except Exception as exc:  # canonical result is already valid and remains authoritative
            _append_stage(
                record,
                "rag_index",
                {
                    "status": "unavailable",
                    "warning": f"{type(exc).__name__}: semantic index unavailable",
                    "source_url": record.source_url,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
    return record
