"""Regression: the distributed worker loads handoffs that carry producer provenance (#426).

Issue #352 taught the schema-version normalizer to fold undeclared ``source`` keys into
``source.extensions``. The worker's handoff loader reads a current-version row straight from
MongoDB and called ``CanonicalRecord.model_validate`` directly, bypassing that fold. Live
backfilled records were therefore rejected terminally at seed with
``source.backfill Extra inputs are not permitted`` and never reached analysis.
"""

from __future__ import annotations

from typing import Any

from laclaugpt_data_analysis.distributed_worker import MongoCollectionHandoff


class _StubCollection:
    def __init__(self, row: dict[str, Any]):
        self._row = row

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        assert query == {"project_id": "ai26", "source_url": self._row["source_url"]}
        return self._row


def _handoff(row: dict[str, Any]) -> MongoCollectionHandoff:
    handoff = object.__new__(MongoCollectionHandoff)
    handoff.collection = _StubCollection(row)
    handoff.project_id = "ai26"
    return handoff


def test_resolve_keeps_undeclared_source_provenance():
    row = {
        "project_id": "ai26",
        "schema_version": "1.2.0",
        "source_url": "https://www.etui.org/news/help-yourself-order-help-others",
        "source": {
            "platform": "rss",
            "language": "en",
            "backfill": "#295",
            "backfilled_at": "20261012T071912Z",
            "raw_metadata": {"feed": "etui"},
        },
        "handoff": {"status": "ready", "published_at": "2026-09-04T00:00:00Z"},
    }

    record = _handoff(row).resolve(row["source_url"])

    assert record.source.platform == "rss"
    assert record.source.language == "en"
    assert record.source.raw_metadata == {"feed": "etui"}
    assert record.source.extensions == {
        "backfill": "#295",
        "backfilled_at": "20261012T071912Z",
    }
    # The row itself is not mutated: provenance stays exactly as the producer wrote it.
    assert row["source"]["backfill"] == "#295"


def test_resolve_without_extensions_is_unchanged():
    row = {
        "project_id": "ai26",
        "source_url": "https://example.org/a",
        "source": {"platform": "web"},
    }

    record = _handoff(row).resolve(row["source_url"])

    assert record.source.extensions == {}
    assert record.source.platform == "web"
