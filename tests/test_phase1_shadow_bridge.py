import json

from laclaugpt_data_analysis.interchange import from_phase0_mongo_document, record_to_json
from laclaugpt_data_analysis.phase1_shadow import (
    adapt_phase0_batch,
    export_phase0_shadow_jsonl,
    preprocess_shadow_record,
)


def _phase0_document():
    return {
        "_id": "mongo-only-id",
        "source_url": "https://example.org/phase0",
        "source_type": "rss",
        "actor_name": "Example Actor",
        "language": "en",
        "title": "Example",
        "document_id": "doc-123",
        "normalized_text": "AI regulation should protect workers.",
        "content_hash": "abc",
        "metadata": {
            "source_url": "https://example.org/phase0",
            "arena": "parliamentary",
            "ai_formation": "critical_ai",
        },
        "phase0": {
            "preprocess": {"status": "ok"},
            "summary": {"status": "ok"},
            "postprocess": {"status": "ok"},
            "discourse": {"status": "ok"},
        },
        "phase0_summary_raw": "{raw summary}",
        "phase0_summary": {
            "summary": "The actor argues for worker-protective AI regulation.",
            "claims": ["AI regulation should protect workers."],
        },
        "phase0_summary_validated": {"summary": "validated"},
        "phase0_discourse_raw": "{raw discourse}",
        "phase0_discourse": {"nodal_points": ["AI regulation"]},
        "phase0_ontology": {"nodes": []},
    }


def test_phase0_mongo_adapter_is_lossless_and_deterministic():
    source = _phase0_document()
    first = from_phase0_mongo_document(source)
    second = from_phase0_mongo_document(source)

    assert first.source_url == source["source_url"]
    assert first.source_native_ids["document_id"] == "doc-123"
    assert first.content.text == source["normalized_text"]
    assert first.source.raw_metadata["arena"] == "parliamentary"
    assert first.analysis.summary == source["phase0_summary"]["summary"]
    assert first.legacy["phase0"]["phase0_discourse_raw"] == "{raw discourse}"
    assert first.intermediate.stage_outputs["phase0"]["phase0_summary_raw"] == "{raw summary}"
    assert "_id" not in first.legacy["phase0"]
    assert record_to_json(first) == record_to_json(second)


def test_shadow_batch_isolates_bad_records_and_preserves_order():
    good_a = _phase0_document()
    good_b = {**_phase0_document(), "source_url": "https://example.org/b", "document_id": "doc-b"}
    bad = {"document_id": "bad-no-text"}

    records, diagnostics = adapt_phase0_batch([good_a, bad, good_b])

    assert [record.source_url for record in records] == [
        "https://example.org/phase0",
        "https://example.org/b",
    ]
    assert len(diagnostics) == 1
    assert diagnostics[0].index == 1
    assert diagnostics[0].document_id == "bad-no-text"


def test_shadow_export_has_no_database_dependency(tmp_path):
    target = tmp_path / "data" / "exports" / "shadow.jsonl"
    diagnostics = export_phase0_shadow_jsonl([_phase0_document()], target)

    assert diagnostics == []
    payload = json.loads(target.read_text(encoding="utf-8").strip())
    assert payload["source_url"] == "https://example.org/phase0"
    assert payload["legacy"]["phase0"]["phase0_discourse"]["nodal_points"] == ["AI regulation"]


def test_shadow_preprocess_is_idempotent_and_provider_free():
    record = from_phase0_mongo_document(_phase0_document())
    first = preprocess_shadow_record(record)
    first_snapshot = record_to_json(first)
    second = preprocess_shadow_record(first)

    assert record_to_json(second) == first_snapshot
    assert len(second.intermediate.stage_outputs["preprocess_contract"]) == 1
    assert second.analysis.summary == "The actor argues for worker-protective AI regulation."
