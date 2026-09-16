from __future__ import annotations

from datetime import UTC, datetime

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.context_orchestration import (
    AnalysisContextPolicy,
    assemble_analysis_context,
    latest_summary_for_record,
)
from laclaugpt_data_analysis.context_runtime import ContextItem
from laclaugpt_data_analysis.periodic_summary import (
    PeriodicSummaryRepository,
    build_periodic_summary,
)
from laclaugpt_data_analysis.rag import RetrievalAudit, RetrievalContext, RetrievalItem
from laclaugpt_data_analysis.storage import CsvStore


class FakeRetrievalBackend:
    def retrieve_context(self, query, filters=None, *, top_k=20, depth=2, mode="hybrid"):
        del query, top_k, depth
        items = [
            RetrievalItem(
                canonical_id="https://example.org/current",
                text="self retrieval must be removed",
                score=0.99,
            ),
            RetrievalItem(
                canonical_id="https://example.org/rejected",
                text="rejected interpretation",
                score=0.9,
                metadata={"review_status": "rejected"},
            ),
            RetrievalItem(
                canonical_id="https://example.org/reviewed",
                text="reviewed related context",
                score=0.8,
                metadata={"review_status": "human_reviewed"},
            ),
        ]
        audit = RetrievalAudit(
            request_id="test-request",
            method=mode,
            filters=dict(filters or {}),
            selected_canonical_ids=[item.canonical_id for item in items],
            scores={item.canonical_id: item.score or 0.0 for item in items},
            graph_paths={},
            embedding_model="fake",
            index_version="test",
            timestamp="2026-09-17T00:00:00+00:00",
            context_size=len(items),
        )
        return RetrievalContext(items=items, audit=audit)


def _record(url: str, when: datetime) -> CanonicalRecord:
    record = CanonicalRecord(source_url=url)
    record.source.created_at = when
    record.content.text = "Current source about AI governance"
    record.source.raw_metadata["formation_hint"] = "researcher prior only"
    return record


def test_historical_summary_selection_uses_record_time(tmp_path) -> None:
    repository = PeriodicSummaryRepository(CsvStore(tmp_path / "summaries.csv"))
    previous_record = _record("https://example.org/old", datetime(2026, 9, 15, 12, tzinfo=UTC))
    summary = build_periodic_summary(
        [previous_record],
        project_id="AI26",
        window_start=datetime(2026, 9, 15, tzinfo=UTC),
        window_end=datetime(2026, 9, 16, tzinfo=UTC),
    )
    repository.save(summary)

    current = _record("https://example.org/current", datetime(2026, 9, 16, 10, tzinfo=UTC))
    selected = latest_summary_for_record(repository, current, project_id="AI26")
    assert selected is not None
    assert selected.id == summary.id

    earlier = _record("https://example.org/earlier", datetime(2026, 9, 15, 10, tzinfo=UTC))
    assert latest_summary_for_record(repository, earlier, project_id="AI26") is None


def test_orchestrator_filters_self_retrieval_rejected_memory_and_labels_priors(tmp_path) -> None:
    project = tmp_path / "project.md"
    theory = tmp_path / "theory.md"
    project.write_text("Project background", encoding="utf-8")
    theory.write_text("Theory rules", encoding="utf-8")
    record = _record("https://example.org/current", datetime(2026, 9, 17, tzinfo=UTC))

    memory = [
        ContextItem(
            kind="prior_record",
            text="rejected memory",
            source="test",
            record_id="r1",
            trust="rejected",
        ),
        ContextItem(
            kind="prior_record",
            text="accepted memory",
            source="test",
            record_id="r2",
            trust="human_reviewed",
        ),
    ]
    policy = AnalysisContextPolicy(
        project_background_path=str(project),
        theory_path=str(theory),
    )
    bundle, adapter = assemble_analysis_context(
        record,
        project_id="AI26",
        stage="discourse",
        task="Analyse discourse candidates",
        policy=policy,
        retrieval_backend=FakeRetrievalBackend(),
        memory_items=memory,
    )

    assert "Project background" in bundle.project_background.text
    assert "Theory rules" in bundle.theory_context.text
    assert "researcher prior only" in bundle.source_profile.text
    assert bundle.source_profile.evidence_role == "context"
    assert "accepted memory" in bundle.memory_context.text
    assert "rejected memory" not in bundle.memory_context.text
    assert "reviewed related context" in bundle.rag_context.text
    assert "self retrieval" not in bundle.rag_context.text
    assert "rejected interpretation" not in bundle.rag_context.text
    assert bundle.provenance["rag_audit"]["request_id"] == "test-request"
    assert bundle.provenance["multimodal_visibility"]["declared"] == "textual_derivatives_only"
    assert adapter.rag_context == bundle.rag_context.text


def test_fast_local_profile_is_a_context_ablation(tmp_path) -> None:
    theory = tmp_path / "theory.md"
    theory.write_text("Theory rules", encoding="utf-8")
    record = _record("https://example.org/current", datetime(2026, 9, 17, tzinfo=UTC))
    policy = AnalysisContextPolicy(profile="fast_local", theory_path=str(theory))

    bundle, _ = assemble_analysis_context(
        record,
        project_id="AI26",
        stage="discourse",
        task="Analyse",
        policy=policy,
        retrieval_backend=FakeRetrievalBackend(),
    )

    assert bundle.theory_context.text == ""
    assert bundle.rag_context.text == ""
    assert bundle.current_source.evidence_role == "source_evidence"
