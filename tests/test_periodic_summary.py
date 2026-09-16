from __future__ import annotations

from datetime import UTC, datetime

from laclaugpt_data_analysis.canonical import CanonicalRecord, DiscourseObject, Relation
from laclaugpt_data_analysis.canonical_pipeline import PipelineContext
from laclaugpt_data_analysis.periodic_summary import (
    PeriodicSummaryRepository,
    SummaryScope,
    build_periodic_summary,
    corpus_windows,
    grouped_summaries,
    inject_summary_context,
    latest_completed_window,
    summary_context_item,
)
from laclaugpt_data_analysis.storage import CsvStore


def _record(
    source_url: str,
    when: datetime,
    *,
    author: str = "alice",
    platform: str = "x",
    signifier: str = "freedom",
    formation: str = "formation-a",
    us: str = "citizens",
    them: str = "elite",
    frontier: str = "bureaucracy",
) -> CanonicalRecord:
    record = CanonicalRecord(source_url=source_url)
    record.source.created_at = when
    record.source.author = author
    record.source.platform = platform
    record.source.language = "en"
    record.analysis.status = "analyzed"
    record.analysis.signifiers = [
        DiscourseObject(object_id=f"s:{source_url}", label=signifier, kind="signifier", evidence_ids=[f"e:{source_url}"])
    ]
    record.analysis.formations = [
        DiscourseObject(object_id=f"f:{source_url}", label=formation, kind="formation")
    ]
    record.analysis.us = [DiscourseObject(object_id=f"u:{source_url}", label=us, kind="collective_subject")]
    record.analysis.them = [DiscourseObject(object_id=f"t:{source_url}", label=them, kind="opposed_subject")]
    record.analysis.frontier = [
        DiscourseObject(object_id=f"fr:{source_url}", label=frontier, kind="frontier")
    ]
    record.analysis.relations = [
        Relation(
            relation_id=f"r:{source_url}",
            relation_type="articulation",
            source_ref=signifier,
            target_ref=us,
            evidence_ids=[f"e:{source_url}"],
        )
    ]
    return record


def test_corpus_windows_follow_corpus_time_and_ignore_input_order() -> None:
    records = [
        _record("b", datetime(2026, 9, 3, 3, tzinfo=UTC)),
        _record("a", datetime(2026, 9, 1, 23, tzinfo=UTC)),
    ]
    windows = corpus_windows(records)
    assert windows == [
        (datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 2, tzinfo=UTC)),
        (datetime(2026, 9, 2, tzinfo=UTC), datetime(2026, 9, 3, tzinfo=UTC)),
        (datetime(2026, 9, 3, tzinfo=UTC), datetime(2026, 9, 4, tzinfo=UTC)),
    ]


def test_latest_completed_window_is_completed_not_partial() -> None:
    start, end = latest_completed_window(datetime(2026, 9, 17, 12, tzinfo=UTC))
    assert start == datetime(2026, 9, 16, tzinfo=UTC)
    assert end == datetime(2026, 9, 17, tzinfo=UTC)


def test_periodic_summary_aggregates_deltas_and_frontier_without_promoting_counts() -> None:
    first = build_periodic_summary(
        [_record("a", datetime(2026, 9, 15, 10, tzinfo=UTC))],
        project_id="demo",
        window_start=datetime(2026, 9, 15, tzinfo=UTC),
        window_end=datetime(2026, 9, 16, tzinfo=UTC),
    )
    second = build_periodic_summary(
        [
            _record("b", datetime(2026, 9, 16, 10, tzinfo=UTC)),
            _record("c", datetime(2026, 9, 16, 11, tzinfo=UTC)),
        ],
        project_id="demo",
        window_start=datetime(2026, 9, 16, tzinfo=UTC),
        window_end=datetime(2026, 9, 17, tzinfo=UTC),
        previous=first,
    )
    assert second.statistics.signifiers[0].delta == 1
    assert second.statistics.frontiers[0].delta == 1
    assert "frequency/centrality" in second.narrative.lower()
    assert second.previous_summary_ids == [first.id]


def test_grouping_is_project_neutral_and_scope_specific() -> None:
    records = [
        _record("a", datetime(2026, 9, 16, 10, tzinfo=UTC), author="alice"),
        _record("b", datetime(2026, 9, 16, 11, tzinfo=UTC), author="bob"),
    ]
    summaries = grouped_summaries(
        records,
        project_id="EP24",
        window_start=datetime(2026, 9, 16, tzinfo=UTC),
        window_end=datetime(2026, 9, 17, tzinfo=UTC),
        group_by=["author", "formation"],
    )
    keys = {item.scope.key for item in summaries}
    assert {"overall", "author=alice", "author=bob", "formation=formation-a"} <= keys


def test_latest_summary_is_context_not_evidence_and_injection_is_provenanced() -> None:
    summary = build_periodic_summary(
        [_record("a", datetime(2026, 9, 16, 10, tzinfo=UTC))],
        project_id="AI26",
        window_start=datetime(2026, 9, 16, tzinfo=UTC),
        window_end=datetime(2026, 9, 17, tzinfo=UTC),
    )
    item = summary_context_item(summary)
    assert item.kind == "historical_summary_context"
    assert item.trust == "context_not_evidence"
    assert "NOT CURRENT-SOURCE EVIDENCE" in item.text

    context = inject_summary_context(PipelineContext(), summary)
    assert summary.id in context.provenance["periodic_summary_id"]
    assert summary.sha256 in context.provenance["periodic_summary_sha256"]
    assert "NOT CURRENT-SOURCE EVIDENCE" in context.situational_context


def test_repository_is_idempotent_and_project_isolated(tmp_path) -> None:
    repo = PeriodicSummaryRepository(CsvStore(tmp_path / "summaries.csv"))
    ai = build_periodic_summary(
        [_record("a", datetime(2026, 9, 16, 10, tzinfo=UTC))],
        project_id="AI26",
        window_start=datetime(2026, 9, 16, tzinfo=UTC),
        window_end=datetime(2026, 9, 17, tzinfo=UTC),
    )
    ep = ai.model_copy(update={"id": "periodic:ep", "project_id": "EP24"})
    repo.save(ai)
    repo.save(ai)
    repo.save(ep)
    assert len(repo.read()) == 2
    assert repo.latest("AI26", SummaryScope()).id == ai.id
    assert repo.latest("EP24", SummaryScope()).id == ep.id
