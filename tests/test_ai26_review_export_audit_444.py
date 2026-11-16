"""Synthetic, offline tests for issue #444's privacy-preserving review audit."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "ai26_review_export_audit", ROOT / "tools" / "ai26_review_export_audit.py"
)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


def fixture(tmp_path, rows=None):
    if rows is None:
        rows = [
            {"source_url": "https://example.invalid/1", "platform": "rss",
             "arena": "elites", "source_text": "Synthetic\ntext",
             "analysis_status": "analyzed", "analysis_summary": "Synthetic summary",
             "review_note": "", "formations": "Synthetic formation"},
            {"source_url": "https://example.invalid/2", "platform": "rss",
             "arena": "grassroots", "source_text": "Other synthetic content",
             "analysis_status": "analyzed", "analysis_summary": "",
             "review_note": "Missing summary", "formations": ""},
        ]
    csv_file = tmp_path / "review.csv"
    fields = list(rows[0])
    with csv_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(json.dumps({
        "schema": "ai26.human_review/1",
        "file_sha256": hashlib.sha256(csv_file.read_bytes()).hexdigest(),
        "exported_rows": len(rows),
    }), encoding="utf-8")
    return csv_file, manifest


def test_reproducible_and_private_aggregates(tmp_path):
    csv_file, manifest = fixture(tmp_path)
    first, sample1 = audit_module.audit(csv_file, manifest, seed=444)
    second, sample2 = audit_module.audit(csv_file, manifest, seed=444)
    assert first == second
    assert sample1 == sample2
    assert first["rows"] == 2
    assert first["missing_by_field"]["analysis_summary"] == 1
    assert first["accuracy_assessed"] is False
    report = json.dumps(first)
    assert "example.invalid" not in report
    assert "Synthetic summary" not in report
    assert "Synthetic\\ntext" not in report


def test_bad_checksum_rejected(tmp_path):
    csv_file, manifest = fixture(tmp_path)
    csv_file.write_text(csv_file.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        audit_module.audit(csv_file, manifest)


def test_duplicate_source_rejected(tmp_path):
    row = {"source_url": "https://example.invalid/1", "platform": "rss",
           "arena": "elites", "source_text": "Test",
           "analysis_status": "analyzed", "analysis_summary": "Test",
           "review_note": ""}
    csv_file, manifest = fixture(tmp_path, [row, row])
    with pytest.raises(ValueError, match="duplicated"):
        audit_module.audit(csv_file, manifest)


def test_main_writes_separate_private_sample(tmp_path):
    csv_file, manifest = fixture(tmp_path)
    report = tmp_path / "aggregate.json"
    sample = tmp_path / "private.csv"
    assert audit_module.main([
        "--input", str(csv_file), "--manifest", str(manifest),
        "--report", str(report), "--private-sample", str(sample)
    ]) == 0
    assert json.loads(report.read_text())["sample_rows"] == 2
    assert "example.invalid" in sample.read_text()
    assert "example.invalid" not in report.read_text()


def test_a_whole_transcript_cell_does_not_break_the_audit(tmp_path):
    """A real export carries whole source texts; the csv default limit is 128 kB.

    On the first live export the audit died with a bare "Error", which says nothing about the cause.
    """
    rows = [
        {"source_url": "https://example.invalid/1", "platform": "rss", "arena": "elites",
         "source_text": "x" * 200_000, "analysis_status": "analyzed",
         "analysis_summary": "Synthetic summary", "review_note": "", "formations": ""},
    ]
    csv_file, manifest = fixture(tmp_path, rows)
    report, _ = audit_module.audit(csv_file, manifest, seed=444)
    assert report["rows"] == 1


def test_field_limit_failure_is_diagnosed_not_echoed(monkeypatch, tmp_path):
    """The failure message must say what broke without quoting a cell."""
    def boom(*_args, **_kwargs):
        raise csv.Error("field larger than field limit (131072)")

    monkeypatch.setattr(audit_module, "audit", boom)
    csv_file, manifest = fixture(tmp_path)
    code = audit_module.main(["--input", str(csv_file), "--manifest", str(manifest),
                              "--report", str(tmp_path / "r.json"),
                              "--private-sample", str(tmp_path / "s.csv")])
    assert code == 2


def test_a_field_empty_in_every_row_is_reported_as_unproduced(tmp_path):
    rows = [
        {"source_url": "https://example.invalid/1", "platform": "rss", "arena": "elites",
         "source_text": "a", "analysis_status": "analyzed", "analysis_summary": "s",
         "review_note": "", "formations": "f", "discourses": ""},
        {"source_url": "https://example.invalid/2", "platform": "rss", "arena": "elites",
         "source_text": "b", "analysis_status": "analyzed", "analysis_summary": "s",
         "review_note": "", "formations": "", "discourses": ""},
    ]
    csv_file, manifest = fixture(tmp_path, rows)
    report, _ = audit_module.audit(csv_file, manifest, seed=444)
    assert report["empty_in_every_row"] == ["discourses"]
    assert "formations" not in report["empty_in_every_row"]


def test_evidence_grounding_is_measured_not_assumed(tmp_path):
    """A paraphrase counts as unverified; the report must say so instead of assuming quotations."""
    rows = [
        {"source_url": "https://example.invalid/1", "platform": "rss", "arena": "elites",
         "source_text": "synthetic source text", "analysis_status": "analyzed",
         "analysis_summary": "s", "review_note": "", "formations": "",
         "evidence_count": "3", "evidence_exact_count": "2"},
        {"source_url": "https://example.invalid/2", "platform": "rss", "arena": "elites",
         "source_text": "other", "analysis_status": "analyzed",
         "analysis_summary": "s", "review_note": "", "formations": "",
         "evidence_count": "2", "evidence_exact_count": "0"},
    ]
    csv_file, manifest = fixture(tmp_path, rows)
    report, _ = audit_module.audit(csv_file, manifest, seed=444)
    evidence = report["evidence"]
    assert evidence["available"] is True
    assert evidence["items"] == 5
    assert evidence["verbatim_in_source"] == 2
    assert evidence["verbatim_share"] == 0.4
    assert evidence["rows_with_no_verbatim_citation"] == 1


def test_evidence_metric_says_so_when_the_export_lacks_the_columns(tmp_path):
    csv_file, manifest = fixture(tmp_path)  # fixture rows carry no evidence columns
    report, _ = audit_module.audit(csv_file, manifest, seed=444)
    assert report["evidence"]["available"] is False
