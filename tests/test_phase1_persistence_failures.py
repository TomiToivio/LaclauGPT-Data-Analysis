import pytest

from laclaugpt_data_analysis.interchange import from_phase0_mongo_document
from laclaugpt_data_analysis.phase1_runtime import (
    load_persisted_phase1_record,
    persist_phase1_failure,
    phase1_persistence_payload,
)


class FakeCollection:
    def __init__(self):
        self.calls = []

    def update_one(self, identity, update, upsert=False):
        self.calls.append((identity, update, upsert))
        return {"ok": 1}


def _source():
    return {
        "_id": "mongo-id",
        "source_url": "https://example.org/phase1-failure",
        "document_id": "doc-1",
        "normalized_text": "AI policy text.",
        "phase0_summary": {"summary": "Phase 0 baseline."},
    }


def test_persisted_phase1_record_reloads_without_recomputation():
    record = from_phase0_mongo_document(_source())
    record.analysis.status = "phase1-summary-only"
    record.analysis.summary = "Persisted Phase 1 summary."
    document = {**_source(), "phase1": phase1_persistence_payload(record)}

    loaded = load_persisted_phase1_record(document)

    assert loaded is not None
    assert loaded.source_url == record.source_url
    assert loaded.analysis.status == "phase1-summary-only"
    assert loaded.analysis.summary == "Persisted Phase 1 summary."
    assert loaded.legacy["phase0"]["phase0_summary"]["summary"] == "Phase 0 baseline."


def test_phase1_failure_write_is_namespaced_and_counts_attempts():
    collection = FakeCollection()

    persist_phase1_failure(
        collection,
        _source(),
        stage="summary",
        error=ValueError("invalid structured output"),
    )

    identity, update, upsert = collection.calls[0]
    assert identity == {"_id": "mongo-id"}
    assert upsert is False
    assert all(key.startswith("phase1.") for key in update["$set"])
    assert all(key.startswith("phase1.") for key in update["$inc"])
    assert update["$set"]["phase1.status"] == "failed"
    assert update["$set"]["phase1.failures.summary.last_error"] == {
        "type": "ValueError",
        "message": "invalid structured output",
    }
    assert update["$inc"]["phase1.failures.summary.attempts"] == 1


def test_phase1_failure_stage_must_be_mongo_safe():
    with pytest.raises(ValueError, match="Mongo-safe"):
        persist_phase1_failure(
            FakeCollection(),
            _source(),
            stage="summary.raw",
            error=RuntimeError("boom"),
        )
