"""Production-facing context orchestration for canonical LLM stages.

The orchestrator is deliberately IO-light: callers provide optional summary repositories,
retrieval backends and memory items. It applies one stage policy, excludes the current
record from retrieved memory, selects historical summaries by corpus time, and returns
both the typed AnalysisContextBundle and the existing PipelineContext adapter.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .analysis_context import AnalysisContextBundle, build_analysis_context_bundle
from .canonical import CanonicalRecord
from .canonical_pipeline import PipelineContext
from .codebooks import CodebookEntry
from .context_runtime import ContextItem, assemble_context, load_text_context
from .periodic_summary import PeriodicDiscourseSummary, PeriodicSummaryRepository, SummaryScope
from .rag import RetrievalBackend

StageName = Literal["frame", "summary", "discourse", "validation", "document"]


class StageContextPolicy(BaseModel):
    use_project_background: bool = True
    use_theory: bool = True
    use_codebook: bool = True
    use_situational_summary: bool = True
    use_memory: bool = True
    use_rag: bool = True
    rag_mode: str = "hybrid"
    rag_top_k: int = Field(default=8, ge=1, le=100)
    rag_depth: int = Field(default=2, ge=1, le=5)


class AnalysisContextPolicy(BaseModel):
    profile: str = "high_accuracy"
    project_background_path: str | None = None
    theory_path: str | None = None
    history_context: int = Field(default=1, ge=0, le=30)
    stages: dict[str, StageContextPolicy] = Field(
        default_factory=lambda: {
            "frame": StageContextPolicy(
                use_theory=False,
                use_situational_summary=False,
                use_memory=False,
                use_rag=False,
            ),
            "summary": StageContextPolicy(rag_top_k=8),
            "discourse": StageContextPolicy(rag_top_k=12),
            "validation": StageContextPolicy(rag_top_k=12),
            "document": StageContextPolicy(rag_top_k=8),
        }
    )

    def for_stage(self, stage: StageName) -> StageContextPolicy:
        return self.stages.get(stage, StageContextPolicy())


def record_time(record: CanonicalRecord) -> datetime | None:
    value = record.source.created_at or record.source.collected_at
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def source_profile_text(record: CanonicalRecord) -> str:
    """Render source/actor metadata as a contextual prior, not evidence of ideology."""
    raw = record.source.raw_metadata
    values = {
        "platform": record.source.platform,
        "source_type": record.source.source_type,
        "author": record.source.author or record.source.author_fullname,
        "language": record.content.language or record.source.language,
        "country": record.source.country,
        "arena": raw.get("arena"),
        "actor_type": raw.get("actor_type"),
        "organization": raw.get("organization"),
        "party": raw.get("party"),
        "researcher_hint": raw.get("formation_hint") or raw.get("source_profile"),
    }
    lines = [
        "Source profile is contextual prior knowledge, not evidence that the current item expresses a formation or stance."
    ]
    lines.extend(f"- {key}: {value}" for key, value in values.items() if value not in (None, ""))
    return "\n".join(lines)


def latest_summary_for_record(
    repository: PeriodicSummaryRepository | None,
    record: CanonicalRecord,
    *,
    project_id: str,
    scope: SummaryScope | None = None,
) -> PeriodicDiscourseSummary | None:
    """Select only a compatible summary completed before the record/corpus timestamp."""
    if repository is None:
        return None
    timestamp = record_time(record)
    if timestamp is None:
        return None
    return repository.latest(project_id, scope or SummaryScope(), before=timestamp)


def _load_resource(path: str | None, kind: str) -> ContextItem | None:
    if not path:
        return None
    source = Path(path)
    if not source.exists():
        return None
    return load_text_context(
        source,
        kind=kind,
        trust="method" if kind == "theory_context" else "context",
    )


def _bounded_items(
    items: list[ContextItem],
    *,
    profile: str,
    kind: Literal["memory", "rag", "summary", "theory"],
) -> tuple[str, dict[str, Any]]:
    kwargs: dict[str, Any] = {"profile": profile}
    if kind == "memory":
        kwargs["previous_records"] = items
    elif kind == "rag":
        kwargs["rag_context"] = items
    elif kind == "summary":
        kwargs["previous_summary"] = items
    else:
        kwargs["theory_context"] = items
    snapshot = assemble_context(**kwargs)
    return snapshot.text, dict(snapshot.provenance)


def _rag_items(
    backend: RetrievalBackend | None,
    record: CanonicalRecord,
    *,
    policy: StageContextPolicy,
    project_id: str,
) -> tuple[list[ContextItem], dict[str, Any]]:
    if backend is None or not policy.use_rag:
        return [], {"status": "disabled"}
    query = record.content.text or record.content.title or record.source_url
    filters = {"project_id": project_id}
    context = backend.retrieve_context(
        query,
        filters=filters,
        top_k=policy.rag_top_k + 1,
        depth=policy.rag_depth,
        mode=policy.rag_mode,
    )
    items: list[ContextItem] = []
    for item in context.items:
        if item.canonical_id == record.source_url:
            continue
        review_status = str(item.metadata.get("review_status") or "model_proposed")
        if review_status.casefold() == "rejected":
            continue
        items.append(
            ContextItem(
                kind="rag_record",
                text=item.text,
                source="retrieval_backend",
                record_id=item.canonical_id,
                trust=review_status,
                metadata={
                    "score": item.score,
                    "graph_path": item.graph_path,
                    **item.metadata,
                },
            )
        )
        if len(items) >= policy.rag_top_k:
            break
    return items, context.audit.to_dict()


def assemble_analysis_context(
    record: CanonicalRecord,
    *,
    project_id: str,
    stage: StageName,
    task: str,
    codebook_entries: list[CodebookEntry] | None = None,
    policy: AnalysisContextPolicy | None = None,
    summary_repository: PeriodicSummaryRepository | None = None,
    retrieval_backend: RetrievalBackend | None = None,
    memory_items: list[ContextItem] | None = None,
) -> tuple[AnalysisContextBundle, PipelineContext]:
    """Build the unified bundle and a backwards-compatible PipelineContext adapter."""
    active = policy or AnalysisContextPolicy()
    stage_policy = active.for_stage(stage)

    project_item = _load_resource(active.project_background_path, "project_background")
    theory_item = _load_resource(active.theory_path, "theory_context")
    project_text = project_item.text if project_item and stage_policy.use_project_background else ""
    theory_text = ""
    theory_provenance: dict[str, Any] = {}
    if theory_item and stage_policy.use_theory:
        theory_text, theory_provenance = _bounded_items(
            [theory_item], profile=active.profile, kind="theory"
        )

    summary = (
        latest_summary_for_record(summary_repository, record, project_id=project_id)
        if stage_policy.use_situational_summary
        else None
    )
    summary_items = (
        [
            ContextItem(
                kind="historical_summary_context",
                text=summary.context_text(),
                source="periodic_summary",
                record_id=summary.id,
                trust="context_not_evidence",
                metadata={
                    "sha256": summary.sha256,
                    "window_end": summary.window_end.isoformat(),
                },
            )
        ]
        if summary
        else []
    )
    situational_text = ""
    summary_provenance: dict[str, Any] = {}
    if summary_items:
        situational_text, summary_provenance = _bounded_items(
            summary_items, profile=active.profile, kind="summary"
        )

    positive_memory = [
        item
        for item in (memory_items or [])
        if item.record_id != record.source_url and item.trust.casefold() != "rejected"
    ]
    memory_text = ""
    memory_provenance: dict[str, Any] = {}
    if stage_policy.use_memory and positive_memory:
        memory_text, memory_provenance = _bounded_items(
            positive_memory, profile=active.profile, kind="memory"
        )

    rag_items, rag_audit = _rag_items(
        retrieval_backend,
        record,
        policy=stage_policy,
        project_id=project_id,
    )
    rag_text = ""
    rag_provenance: dict[str, Any] = {}
    if rag_items:
        rag_text, rag_provenance = _bounded_items(
            rag_items, profile=active.profile, kind="rag"
        )

    bundle = build_analysis_context_bundle(
        record,
        task=task,
        project_background=project_text,
        theory_context=theory_text,
        source_profile=source_profile_text(record),
        codebook_entries=(codebook_entries or []) if stage_policy.use_codebook else [],
        situational_summary=situational_text,
        memory_context=memory_text,
        rag_context=rag_text,
        profile=active.profile,
        provenance={
            "stage": stage,
            "project_id": project_id,
            "theory": theory_provenance,
            "summary": summary_provenance,
            "memory": memory_provenance,
            "rag": rag_provenance,
            "rag_audit": rag_audit,
            "multimodal_visibility": {
                "declared": "textual_derivatives_only",
                "note": "Actual pixel/audio visibility must be set by the provider adapter when binary media is attached.",
            },
        },
    )
    adapter = PipelineContext(
        project_context="\n\n".join(
            value
            for value in (bundle.project_background.text, bundle.theory_context.text)
            if value
        ),
        source_context="\n\n".join(
            value
            for value in (bundle.source_profile.text, bundle.codebook_context.text)
            if value
        ),
        situational_context=bundle.situational_summary.text,
        memory_context=bundle.memory_context.text,
        rag_context=bundle.rag_context.text,
        provenance={
            "project": [
                bundle.project_background.provenance_token(),
                bundle.theory_context.provenance_token(),
            ],
            "source": [
                bundle.source_profile.provenance_token(),
                bundle.codebook_context.provenance_token(),
            ],
            "situational": [bundle.situational_summary.provenance_token()],
            "memory": [bundle.memory_context.provenance_token()],
            "rag": [bundle.rag_context.provenance_token()],
            "task": [bundle.task_contract.provenance_token()],
        },
    )
    return bundle, adapter
