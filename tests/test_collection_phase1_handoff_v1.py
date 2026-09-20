"""Consume the exact Phase 1 Collection handoff fixture.

This file is intentionally paired with
TomiToivio/LaclauGPT-Data-Collection/tests/fixtures/ai26_phase1_handoff_v1.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.interchange import from_collection_record

FIXTURE = Path(__file__).parent / "fixtures" / "ai26_phase1_handoff_v1.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_exact_collection_phase1_fixture_is_consumed_without_source_reshaping() -> None:
    payload = _payload()
    record = from_collection_record(payload)

    assert payload["contract_version"] == "ai26-phase1-handoff-v1"
    assert record.schema_version == SCHEMA_VERSION
    assert record.source_url == payload["source_url"]
    assert record.source_native_ids == payload["source_native_ids"]
    assert record.source.platform == payload["source"]["platform"]
    assert record.source.source_type == payload["source"]["source_type"]
    assert record.source.author == payload["source"]["author"]
    assert record.source.language == payload["source"]["language"]
    assert record.content.text == payload["content"]["text"]
    assert record.content.language == payload["content"]["language"]

    frame = record.content.frames[0]
    assert frame.timestamp_seconds == payload["content"]["frames"][0]["frame_timestamp_seconds"]
    assert frame.media_ref == payload["content"]["frames"][0]["media_ref"]

    media = record.content.media_references[0]
    assert media.kind == payload["content"]["media_references"][0]["kind"]
    assert media.media_type == payload["content"]["media_references"][0]["media_type"]
    assert media.ref == payload["content"]["media_references"][0]["ref"]

    assert record.raw_capture.ref == payload["raw_capture"]["ref"]
    assert record.provenance[0].provenance_id == payload["provenance"][0]["provenance_id"]


def test_collection_neutral_extensions_survive_in_legacy_namespace() -> None:
    payload = _payload()
    record = from_collection_record(payload)

    assert record.legacy["cross_module_source_units"] == []
    assert record.legacy["cross_module_alignments"] == []
    assert record.legacy["cross_module_extensions"]["contract_version"] == (
        "ai26-phase1-handoff-v1"
    )


def test_additive_collection_fields_are_tolerated_without_becoming_analysis_fields() -> None:
    payload = _payload()
    payload["producer_extension"] = {"future_field": "still-safe"}

    record = from_collection_record(payload)

    assert record.legacy["cross_module_extensions"]["producer_extension"] == {
        "future_field": "still-safe"
    }
    assert "producer_extension" not in record.analysis.model_dump(mode="json")


def test_phase1_collection_input_does_not_require_phase0_flat_fields() -> None:
    payload = _payload()
    for phase0_only in ("document_id", "normalized_text", "phase0_summary", "phase0_discourse"):
        assert phase0_only not in payload

    record = from_collection_record(payload)
    assert record.source_url == payload["source_url"]
