from __future__ import annotations

from datetime import UTC, datetime

from laclaugpt_data_analysis.distributed_worker import ready_handoff_query
from laclaugpt_data_analysis.phase1_laskin_runtime import load_ai26_runtime_policy


def test_ai26_laskin_runtime_uses_canonical_phase1_profile():
    policy = load_ai26_runtime_policy()
    assert policy.study_id == "ai26"
    assert policy.phase == "phase-1"
    assert policy.date_after == "2026-09-01T00:00:00+00:00"
    assert policy.report_enabled is True
    assert policy.report_interval_hours == 24
    assert {
        "signifier",
        "formation",
        "author",
        "arena",
        "language",
        "region",
        "topic",
    } <= set(policy.report_group_by)
    assert policy.config_revision
    assert policy.codebook_revision


def test_ready_handoff_query_uses_configured_strict_date_boundary():
    query = ready_handoff_query(
        project_id="ai26",
        run_id="run-1",
        not_before=datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
    )
    assert query["project_id"] == "ai26"
    assert query["handoff.run_id"] == "run-1"
    assert query["handoff.status"] == "ready"
    assert query["handoff.published_at"] == {"$gt": "2026-09-01T00:00:00+00:00"}


def test_ready_handoff_query_can_run_without_a_date_filter():
    query = ready_handoff_query(project_id="demo", run_id="run-2", not_before=None)
    assert "handoff.published_at" not in query
