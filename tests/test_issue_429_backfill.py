"""Regression coverage for #429: bounded old-tail backfill without widening Phase 1."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from laclaugpt_data_analysis.distributed_worker import (
    MongoCollectionHandoff,
    ready_handoff_query,
)


def test_default_query_remains_unchanged():
    assert ready_handoff_query(project_id="ai26") == {
        "project_id": "ai26", "handoff.status": "ready"
    }


def test_backfill_window_keeps_project_readiness_floor_and_platform():
    assert ready_handoff_query(
        project_id="ai26",
        run_id="capture-provenance-not-filter",
        not_before="2026-09-01T00:00:00+00:00",
        before="2026-11-01T00:00:00+00:00",
        platform="bluesky",
    ) == {
        "project_id": "ai26",
        "handoff.status": "ready",
        "source.platform": "bluesky",
        "handoff.published_at": {
            "$gt": "2026-09-01T00:00:00+00:00",
            "$lt": "2026-11-01T00:00:00+00:00",
        },
    }


@pytest.mark.parametrize("before", [
    "2026-09-01T00:00:00+00:00",
    "2026-08-31T00:00:00+00:00",
])
def test_empty_or_inverted_backfill_window_fails_loudly(before):
    with pytest.raises(ValueError, match="HANDOFF_BEFORE"):
        ready_handoff_query(
            project_id="ai26",
            not_before="2026-09-01T00:00:00+00:00",
            before=before,
        )


class Cursor:
    def __init__(self):
        self.order = None
        self.offset = None
        self.count = None

    def sort(self, order):
        self.order = order
        return self

    def skip(self, offset):
        self.offset = offset
        return self

    def limit(self, limit):
        self.count = limit
        return self

    def __iter__(self):
        return iter([{"handoff": {"handoff_key": "old-document"}}])


class Collection:
    def __init__(self):
        self.query = None
        self.cursor = Cursor()

    def find(self, query, projection):
        self.query = query
        assert projection == {"handoff": 1, "_id": 0}
        return self.cursor


@pytest.mark.parametrize("before,expected_direction", [
    (None, -1),
    ("2026-11-01T00:00:00+00:00", 1),
])
def test_backfill_uses_oldest_first_within_priority_only_when_enabled(before, expected_direction):
    handoff = MongoCollectionHandoff.__new__(MongoCollectionHandoff)
    handoff.collection = Collection()
    handoff.project_id = "ai26"
    handoff.not_before = "2026-09-01T00:00:00+00:00"
    handoff.platform = "bluesky"
    handoff.before = before
    assert handoff.ready_handoffs("analysis-run", limit=10, offset=20) == [
        {"handoff_key": "old-document"}
    ]
    assert handoff.collection.query["source.platform"] == "bluesky"
    assert handoff.collection.cursor.order == [
        ("handoff.source_priority", 1),
        ("handoff.published_at", expected_direction),
        ("source_url", 1),
    ]
    assert handoff.collection.cursor.offset == 20
    assert handoff.collection.cursor.count == 10
