"""Issue #488: stored identities and default-reader-safe researcher bundles."""
import csv
import json

import pytest

from laclaugpt_data_analysis.bundle_audit import audit_research_bundle
from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.exporters import write_research_bundle
from laclaugpt_data_analysis.phase1_laskin_report import _decode_result


def _source(number: int) -> str:
    return f"https://example.invalid/synthetic/{number}"


def test_envelope_source_url_restores_distinct_canonical_identities():
    results = [
        _decode_result({
            "source_url": _source(i),
            "result": {"analysis": {"status": "analyzed"}, "content": {"text": "sample"}},
        })
        for i in range(50)
    ]
    assert all(record is not None for record in results)
    assert [record.source_url for record in results] == [_source(i) for i in range(50)]


def test_missing_or_conflicting_source_urls_fail_closed():
    assert _decode_result({"result": {"content": {"text": "sample"}}}) is None
    assert _decode_result({
        "source_url": _source(1),
        "result": {"source_url": _source(2), "content": {"text": "sample"}},
    }) is None


def test_large_source_text_is_lossless_in_jsonl_and_bounded_in_csv(tmp_path):
    oversized = "a" * 160_000
    records = [
        CanonicalRecord(source_url=_source(1), content={"text": oversized}),
        CanonicalRecord(source_url=_source(2), content={"text": "short"}),
    ]
    paths = write_research_bundle(records, tmp_path)
    with paths["csv"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))  # default limit, no field_size_limit calls
    assert len(rows) == 2
    assert rows[0]["source_url"] == _source(1)
    assert json.loads(rows[0]["content"])["_csv_view_truncated"] is True
    with paths["jsonl"].open(encoding="utf-8") as handle:
        canonical = [json.loads(line) for line in handle]
    assert canonical[0]["content"]["text"] == oversized
    assert audit_research_bundle(tmp_path)["ok"] is True


def test_duplicate_source_urls_are_rejected_before_artifacts(tmp_path):
    with pytest.raises(ValueError, match="duplicate source identities"):
        write_research_bundle([
            CanonicalRecord(source_url=_source(1)),
            CanonicalRecord(source_url=_source(1)),
        ], tmp_path)
    assert not (tmp_path / "analysis.jsonl").exists()
