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


def test_compact_review_projection_uses_excerpt_and_singular_formation(tmp_path):
    rows = [
        {"source_url": "https://example.invalid/compact", "platform": "rss",
         "arena": "elites", "text_excerpt": "Only 600 source characters",
         "summary": "Synthetic reading", "formation": "provisional formation",
         "discourse_status": "analyzed"},
        {"source_url": "https://example.invalid/uncoded", "platform": "web",
         "arena": "grassroots", "text_excerpt": "", "summary": "Other summary",
         "formation": "", "discourse_status": "skipped"},
    ]
    csv_file, manifest = fixture(tmp_path, rows)
    report, sample = audit_module.audit(csv_file, manifest)
    assert report["rows"] == 2
    assert report["missing_by_field"]["source_text"] == 1
    assert report["missing_by_field"]["formations"] == 1
    assert report["source_text_is_excerpt"] is True
    assert report["projected_columns"]["formations"] == "formation"
    assert report["statuses"] == {"analyzed": 1, "skipped": 1}
    assert len(sample) == 2


def test_lfs_pointer_requires_hydration(tmp_path):
    csv_file, manifest = fixture(tmp_path)
    manifest.write_text("version https://git-lfs.github.com/spec/v1\\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Git LFS manifest pointer"):
        audit_module.audit(csv_file, manifest)


def test_missing_manifest_digest_fails_closed(tmp_path):
    csv_file, manifest = fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    del payload["file_sha256"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        audit_module.audit(csv_file, manifest)


def test_missing_both_evidence_text_columns_is_error(tmp_path):
    row = {"source_url": "https://example.invalid/1",
           "summary": "Synthetic result", "platform": "rss"}
    csv_file, manifest = fixture(tmp_path, [row])
    with pytest.raises(ValueError, match="source evidence"):
        audit_module.audit(csv_file, manifest)
