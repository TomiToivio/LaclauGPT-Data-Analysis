"""Regression: open producer source contract must survive strict normalization (#352)."""

from laclaugpt_data_analysis.schema_version import normalize_schema_version


def test_collection_source_extensions_survive_normalization_and_round_trip():
    payload = {
        "schema_version": "1.2.0",
        "source_url": "https://example.org/research-item/1",
        "source": {
            "platform": "web",
            "backfill": "#250",
            "backfilled_at": "20261012T071912Z",
            "future_provenance_key": {"reason": "replay", "batch": 2},
            "raw_metadata": {"collector_note": "keep"},
        },
    }
    record = normalize_schema_version(payload)
    assert record.source.platform == "web"
    assert record.source.raw_metadata["collector_note"] == "keep"
    assert record.source.raw_metadata["collection_source_extensions"] == {
        "backfill": "#250",
        "backfilled_at": "20261012T071912Z",
        "future_provenance_key": {"reason": "replay", "batch": 2},
    }
    normalized = record.canonical_dict()
    assert normalize_schema_version(normalized).canonical_dict() == normalized
    # Caller input remains unchanged.
    assert payload["source"]["backfill"] == "#250"


def test_no_source_extensions_preserves_existing_metadata():
    payload = {
        "schema_version": "1.1.0",
        "source_url": "https://example.org/research-item/2",
        "source": {"platform": "rss", "raw_metadata": {"origin": "feed"}},
    }
    record = normalize_schema_version(payload)
    assert record.source.raw_metadata == {"origin": "feed"}
    assert record.schema_version == "1.2.0"
