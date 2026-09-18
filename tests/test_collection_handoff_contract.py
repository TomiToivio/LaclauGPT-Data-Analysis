"""Pin the Collection -> Analysis Phase 1 AI26 handoff contract.

Closes the Analysis half of TomiToivio/LaclauGPT-Data-Collection#75.

Collection and Analysis define **separate** model classes with the same names. An
adapter (`from_collection_record`) bridges them, but nothing exercised that
boundary, so the two schemas could drift apart while both repositories' local
suites stayed green.

This test converts a synthetic AI26 collection record through the real adapter and
asserts that nothing the issue names is lost: source identity, native IDs,
timestamps, language/source metadata, media/frame references and provenance.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laclaugpt_data_analysis.interchange import from_collection_record

FIXTURE = Path(__file__).parent / "fixtures" / "ai26_collection_handoff_v1.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# The authoritative handoff schema is versioned
# --------------------------------------------------------------------------

def test_fixture_declares_the_handoff_contract_version() -> None:
    payload = _payload()
    assert payload["schema_version"] == "1.1.0-draft"
    assert payload["handoff"]["contract_version"] == "1.0"


def test_fixture_is_collection_neutral() -> None:
    """Collection must not carry Laclaudian analytical fields (#75)."""
    payload = _payload()
    forbidden = (
        "formations", "signifiers", "nodal_points", "empty_signifier",
        "floating_signifier", "equivalence", "antagonism", "formula_of_populism",
    )
    blob = json.dumps(payload).casefold()
    for field in forbidden:
        assert field not in blob, f"Collection record must not carry {field!r}"


# --------------------------------------------------------------------------
# Nothing the issue names may be lost across the boundary
# --------------------------------------------------------------------------

def test_adapter_preserves_source_identity() -> None:
    payload = _payload()
    record = from_collection_record(payload)
    assert record.source_url == payload["source_url"]


def test_adapter_preserves_native_ids() -> None:
    payload = _payload()
    record = from_collection_record(payload)
    assert record.source_native_ids == payload["source_native_ids"]


def test_adapter_preserves_created_at() -> None:
    payload = _payload()
    record = from_collection_record(payload)
    assert record.source.created_at is not None
    assert record.source.created_at.isoformat().startswith("2026-09-18")


def test_adapter_preserves_source_metadata() -> None:
    payload = _payload()
    record = from_collection_record(payload)
    assert record.source.platform == payload["source"]["platform"]
    assert record.source.author == payload["source"]["author"]
    assert record.source.language == payload["source"]["language"]


def test_adapter_preserves_text_and_language() -> None:
    payload = _payload()
    record = from_collection_record(payload)
    assert record.content.text == payload["content"]["text"]
    assert record.content.language == payload["content"]["language"]


def test_adapter_preserves_media_references() -> None:
    payload = _payload()
    record = from_collection_record(payload)
    assert len(record.content.media_references) == len(payload["content"]["media_references"])
    incoming = payload["content"]["media_references"][0]
    media = record.content.media_references[0]
    assert media.kind == incoming["kind"]
    assert media.url == incoming["url"]
    assert media.object_ref == incoming["object_ref"]


def test_adapter_preserves_media_type_and_ref() -> None:
    """The specific divergence pinned by #75.

    Collection's MediaReference carries `media_type` and `ref`; Analysis's did not,
    and Analysis models forbid extra fields — so conversion of a real record raised
    a ValidationError instead of losing data quietly.
    """
    payload = _payload()
    record = from_collection_record(payload)
    incoming = payload["content"]["media_references"][0]
    media = record.content.media_references[0]
    assert media.media_type == incoming["media_type"]
    assert media.ref == incoming["ref"]


def test_adapter_preserves_provenance() -> None:
    payload = _payload()
    record = from_collection_record(payload)
    assert record.provenance, "collection provenance must survive the boundary"
    joined = json.dumps([p.model_dump(mode="json") for p in record.provenance])
    assert payload["provenance"][0]["method"] in joined
    assert payload["provenance"][0]["provenance_id"] in joined


def test_adapter_preserves_raw_reference() -> None:
    payload = _payload()
    record = from_collection_record(payload)
    assert record.raw_capture.ref == payload["raw_capture"]["ref"]


def test_adapter_preserves_frames() -> None:
    payload = _payload()
    record = from_collection_record(payload)
    frames = payload["content"].get("frames") or []
    if frames:
        assert len(record.content.frames) == len(frames)
        assert record.content.frames[0].media_ref == frames[0]["media_ref"]
        assert record.content.frames[0].timestamp_seconds == frames[0]["frame_timestamp_seconds"]


def test_adapter_preserves_the_handoff_envelope() -> None:
    """The delivery envelope is transport metadata, not record content (#75).

    It must not be silently dropped, and it must not be mistaken for a canonical
    record field — Analysis forbids extra fields.
    """
    payload = _payload()
    record = from_collection_record(payload)
    assert record.legacy["collection_handoff"]["contract_version"] == "1.0"


# --------------------------------------------------------------------------
# The real Collection fixture must also convert
# --------------------------------------------------------------------------

def test_shared_cross_module_fixture_converts() -> None:
    """The fixture Collection itself validates must survive this adapter.

    Collection's `test_canonical_contract.py` asserts
    `media_references[0].media_type == "video"` on this same fixture; before the
    fix, Analysis raised ``ValidationError: media_type Extra inputs are not
    permitted`` on it — the two repositories disagreed about the same bytes.
    """
    shared = FIXTURE.parent / "canonical_parity_v1.json"
    if not shared.is_file():
        pytest.skip("shared parity fixture not vendored in this repository")
    payload = json.loads(shared.read_text(encoding="utf-8"))
    record = from_collection_record(payload)
    assert record.source_url == payload["source_url"]
    assert record.source_native_ids == payload["source_native_ids"]
