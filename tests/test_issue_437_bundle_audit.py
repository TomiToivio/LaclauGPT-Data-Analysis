"""Synthetic, privacy-safe regression tests for upstream EP24 export QA class (#437)."""
from __future__ import annotations

import csv
import json

from laclaugpt_data_analysis.bundle_audit import audit_research_bundle, main


def _bundle(tmp_path, json_ids=("https://example.test/a",), csv_ids=None, reports=None):
    csv_ids = json_ids if csv_ids is None else csv_ids
    reports = len(json_ids) if reports is None else reports
    (tmp_path / "analysis.jsonl").write_text(
        "".join(json.dumps({"source_url": key}) + "\n" for key in json_ids),
        encoding="utf-8",
    )
    with (tmp_path / "analysis_researchers.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_url"])
        writer.writeheader()
        writer.writerows({"source_url": key} for key in csv_ids)
    report_dir = tmp_path / "analysis_reports"
    report_dir.mkdir()
    for index in range(reports):
        (report_dir / f"{index:06d}.md").write_text("synthetic", encoding="utf-8")


def test_valid_bundle_counts_and_hashes(tmp_path):
    _bundle(tmp_path)
    result = audit_research_bundle(tmp_path)
    assert result["ok"] is True
    assert result["counts"] == {"jsonl": 1, "csv": 1, "reports": 1}
    assert len(result["sha256"]["jsonl"]) == 64
    assert main([str(tmp_path)]) == 0


def test_bom_header_is_accepted(tmp_path):
    _bundle(tmp_path)
    path = tmp_path / "analysis_researchers.csv"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert audit_research_bundle(tmp_path)["ok"] is True


def test_mismatched_rows_and_reports_fail_without_leaking_ids(tmp_path):
    private_id = "https://private.example.test/very-sensitive-source"
    _bundle(tmp_path, json_ids=(private_id, private_id), csv_ids=("different",), reports=1)
    result = audit_research_bundle(tmp_path)
    assert result["ok"] is False
    assert "jsonl_duplicate_identity" in result["problems"]
    assert "jsonl_csv_identity_mismatch" in result["problems"]
    assert "report_count_mismatch" in result["problems"]
    assert private_id not in json.dumps(result)


def test_broken_jsonl_is_a_failure_not_a_success(tmp_path):
    _bundle(tmp_path)
    (tmp_path / "analysis.jsonl").write_text('{"source_url":', encoding="utf-8")
    result = audit_research_bundle(tmp_path)
    assert result["ok"] is False
    assert "jsonl_unreadable_or_invalid" in result["problems"]


def test_missing_artifacts_fail_closed(tmp_path):
    result = audit_research_bundle(tmp_path)
    assert result["ok"] is False
    assert set(result["problems"]) == {
        "jsonl_missing", "csv_missing", "reports_directory_missing"
    }
    assert main([str(tmp_path)]) == 1


def test_csv_missing_identity_header_fails(tmp_path):
    _bundle(tmp_path)
    (tmp_path / "analysis_researchers.csv").write_text("not_identity\nvalue\n", encoding="utf-8")
    result = audit_research_bundle(tmp_path)
    assert not result["ok"]
    assert "csv_source_url_header_missing" in result["problems"]
