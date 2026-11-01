"""#407: a bounded cycle must be able to reach a stratum that priority puts last.

The X records are `source_priority=3`; 2,652 higher-priority ready records sit ahead of them. A worker that
claims ten tasks an hour can never reach the stratum it is meant to repair, so the fix for "X is never seeded"
would be untestable in production. The scoped filter exists for that, and only for that: it narrows the ready
query, it never widens it.
"""
from __future__ import annotations

from laclaugpt_data_analysis.distributed_worker import ready_handoff_query


def test_project_scope_is_the_default_and_has_no_platform_filter():
    query = ready_handoff_query(project_id="ai26", run_id=None, not_before=None)
    assert query == {"project_id": "ai26", "handoff.status": "ready"}
    assert "source.platform" not in query


def test_a_platform_filter_narrows_the_same_ready_query():
    query = ready_handoff_query(project_id="ai26", run_id=None, not_before=None, platform="x")
    assert query["source.platform"] == "x"
    assert query["handoff.status"] == "ready"
    assert "handoff.run_id" not in query, "the capture-run bug must not return with the filter"


def test_the_platform_filter_composes_with_the_date_floor():
    query = ready_handoff_query(project_id="ai26", run_id=None,
                                not_before="2026-09-01T00:00:00+00:00", platform="x")
    assert query["handoff.published_at"] == {"$gt": "2026-09-01T00:00:00+00:00"}


def test_no_filter_means_no_platform_key():
    for platform in (None, ""):
        assert "source.platform" not in ready_handoff_query(
            project_id="ai26", run_id=None, not_before=None, platform=platform)
