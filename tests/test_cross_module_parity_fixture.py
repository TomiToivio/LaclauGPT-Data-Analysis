import json
from pathlib import Path

from laclaugpt_data_analysis.interchange import (
    read_csv,
    read_jsonl,
    read_sqlite,
    record_from_json,
    write_csv,
    write_jsonl,
    write_sqlite,
)
from laclaugpt_data_analysis.research_record import ensure_research_layers

FIXTURE = Path(__file__).parent / "fixtures" / "canonical_parity_v1.json"


def _assert_invariants(record) -> None:
    assert record.source_url == "https://example.invalid/laclaugpt/synthetic/record-001"
    assert record.source_native_ids["legacy_document_id"] == "legacy-001"
    assert record.source.raw_metadata["legacy_optional_field"] == "must-survive-roundtrip"
    assert record.content.transcripts[0].text == "A synthetic transcript segment."
    assert record.content.ocr[0].text == "SYNTHETIC ONLY"
    assert record.content.frames[0].media_ref == "fixture://canonical-parity-v1/frame/002"
    assert record.content.media_references[0].object_ref == "fixture://canonical-parity-v1/media/video"
    assert record.review.status == "PROVISIONAL"
    assert "synthetic-codebook@1.0.0" in record.analysis.codebook_refs
    assert record.analysis.model_runs[0]["provider"] == "fake"
    assert record.analysis.model_runs[0]["model"] == "fixture-model"
    assert any("model_confidence" in item for item in record.analysis.uncertainty)
    shared = record.analysis.plugin_results["cross_module_fixture"]
    candidate = shared["analysis_objects"][0]
    assert candidate["epistemic_type"] == "CANDIDATE_INTERPRETATION"
    assert candidate["review_status"] == "PROVISIONAL"
    assert candidate["metadata"]["legacy_optional_score"] == 0.42
    assert record.evidence[0].metadata["to_id"] == "unit_text_001"
    assert record.legacy["cross_module_review_events"][0]["new_status"] == "PROVISIONAL"


def test_shared_fixture_normalizes_through_analysis_canonical_path() -> None:
    record = record_from_json(FIXTURE.read_text(encoding="utf-8"))
    _assert_invariants(record)


def test_shared_fixture_round_trips_local_storage_adapters(tmp_path) -> None:
    record = ensure_research_layers(record_from_json(FIXTURE.read_text(encoding="utf-8")))
    reference = record.canonical_dict()

    jsonl = tmp_path / "fixture.jsonl"
    write_jsonl(jsonl, [record])
    from_jsonl = read_jsonl(jsonl)[0]
    _assert_invariants(from_jsonl)
    assert from_jsonl.canonical_dict() == reference

    csv = tmp_path / "fixture.csv"
    write_csv(csv, [record])
    from_csv = read_csv(csv)[0]
    _assert_invariants(from_csv)
    assert from_csv.canonical_dict() == reference

    sqlite = tmp_path / "fixture.sqlite3"
    write_sqlite(sqlite, [record])
    from_sqlite = read_sqlite(sqlite)[0]
    _assert_invariants(from_sqlite)
    assert from_sqlite.canonical_dict() == reference


def test_fake_provider_path_is_network_free_and_deterministic() -> None:
    record = record_from_json(FIXTURE.read_text(encoding="utf-8"))
    run = record.analysis.model_runs[0]
    assert run == {
        "run_id": "synthetic-model-run-001",
        "provider": "fake",
        "model": "fixture-model",
        "prompt_version": "fixture-prompt-v1",
        "codebook_ref": "synthetic-codebook@1.0.0",
    }
    serialized = json.dumps(record.canonical_dict(), sort_keys=True)
    assert "ollama" not in serialized.lower()
    assert "openai" not in serialized.lower()
    assert "anthropic" not in serialized.lower()
