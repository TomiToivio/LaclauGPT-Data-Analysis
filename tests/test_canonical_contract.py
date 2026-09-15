from datetime import UTC, datetime

import pytest

from laclaugpt_data_analysis.canonical import (
    CanonicalRecord,
    DiscourseObject,
    Evidence,
    SourceSection,
    Transcript,
)
from laclaugpt_data_analysis.interchange import (
    from_collection_record,
    from_ep24_legacy,
    from_mongo_document,
    read_csv,
    read_jsonl,
    read_sqlite,
    record_from_json,
    record_to_json,
    to_mongo_document,
    write_csv,
    write_jsonl,
    write_sqlite,
)
from laclaugpt_data_analysis.models import ClassificationResult, Provenance
from laclaugpt_data_analysis.schema_version import (
    UnsupportedSchemaVersion,
    normalize_schema_version,
)


def sample_record() -> CanonicalRecord:
    source_url = "https://example.invalid/post/42"
    record = CanonicalRecord(
        source_url=source_url,
        source_native_ids={"document_id": "42"},
        source=SourceSection(platform="synthetic", author="researcher", language="en"),
        provenance=[
            Provenance(method="synthetic", created_at=datetime(2026, 9, 15, tzinfo=UTC))
        ],
    )
    record.content.text = "A synthetic political statement."
    record.content.transcripts = [
        Transcript(id="t1", text="Synthetic transcript", language="en", provider="fake-asr")
    ]
    record.evidence = [
        Evidence(evidence_id="e1", kind="text-span", source_url=source_url, quote="synthetic")
    ]
    record.analysis.status = "analyzed"
    record.analysis.summary = "Synthetic summary"
    record.analysis.classifications = [
        ClassificationResult(
            label="example",
            source_url=source_url,
            confidence=0.75,
            task="synthetic",
        )
    ]
    record.analysis.formations = [
        DiscourseObject(
            object_id="formation_1",
            label="synthetic formation",
            kind="formation",
            evidence_ids=["e1"],
        )
    ]
    record.analysis.uncertainty = ["Synthetic ambiguity"]
    record.review.status = "PROVISIONAL"
    return record


def assert_same_record(left: CanonicalRecord, right: CanonicalRecord) -> None:
    assert right.canonical_dict() == left.canonical_dict()
    assert right.source_url == left.source_url


def test_json_round_trip_preserves_identity_and_analysis() -> None:
    record = sample_record()
    assert_same_record(record, record_from_json(record_to_json(record)))


def test_csv_jsonl_and_sqlite_round_trip(tmp_path) -> None:
    record = sample_record()

    csv_path = tmp_path / "record.csv"
    write_csv(csv_path, [record])
    assert_same_record(record, read_csv(csv_path)[0])

    jsonl_path = tmp_path / "record.jsonl"
    write_jsonl(jsonl_path, [record])
    assert_same_record(record, read_jsonl(jsonl_path)[0])

    db_path = tmp_path / "record.sqlite3"
    write_sqlite(db_path, [record])
    assert_same_record(record, read_sqlite(db_path)[0])


def test_mongo_like_document_round_trip_ignores_backend_id() -> None:
    record = sample_record()
    document = to_mongo_document(record)
    document["_id"] = "backend-only-id"
    assert_same_record(record, from_mongo_document(document))


def test_collection_adapter_preserves_source_url_and_core_fields() -> None:
    incoming = {
        "schema_version": "1.0",
        "document_id": "abc",
        "platform": "synthetic",
        "author": "example",
        "author_fullname": "Example Person",
        "source_url": "https://example.invalid/item/abc",
        "text": "Collected text",
        "language": "en",
        "engagement": {"likes": 2},
        "media_references": [
            {"kind": "image", "url": "https://example.invalid/media.jpg", "media_index": 0}
        ],
        "collection_provenance": {"collector": "synthetic-collector", "collector_version": "1"},
    }
    record = from_collection_record(incoming)
    assert record.source_url == incoming["source_url"]
    assert record.source_native_ids["document_id"] == "abc"
    assert record.source.platform == "synthetic"
    assert record.content.text == "Collected text"
    assert record.content.media_references[0].kind == "image"
    assert record.provenance[0].metadata["stage"] == "collection"


def test_text_only_record_is_first_class() -> None:
    record = CanonicalRecord(source_url="file+sha256:synthetic", content={"text": "text only"})
    assert record.content.transcripts == []
    assert record.content.ocr == []
    assert record.content.frames == []


def test_legacy_ep24_numbered_fields_become_structured_lists() -> None:
    record = from_ep24_legacy(
        {
            "authorUniqueId": "fake-author",
            "videoId": "123",
            "videoDescription": "Synthetic EP24-style row",
            "whisper_transcript": "Synthetic speech",
            "whisper_language": "en",
            "ocr_1": "Synthetic poster",
            "frame_analysis_1": "A synthetic frame description",
            "summary_analysis": "Synthetic analysis",
        }
    )
    assert record.source_url == "tiktok:fake-author:123"
    assert len(record.content.transcripts) == 1
    assert len(record.content.ocr) == 1
    assert len(record.content.frames) == 1
    assert record.analysis.summary == "Synthetic analysis"
    assert "ocr_1" not in record.canonical_dict()


def test_schema_version_transition_is_explicit() -> None:
    payload = sample_record().canonical_dict()
    payload["schema_version"] = "1.0"
    migrated = normalize_schema_version(payload)
    assert migrated.schema_version == "1.0.0"


def test_unknown_schema_version_is_rejected() -> None:
    payload = sample_record().canonical_dict()
    payload["schema_version"] = "99.0.0"
    with pytest.raises(UnsupportedSchemaVersion):
        normalize_schema_version(payload)
