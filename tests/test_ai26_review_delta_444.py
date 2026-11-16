"""Tests for the review-export delta tool (#444).

Two properties matter and both are easy to get wrong: reading a real export (whose cells are whole
source texts, well past csv's 128 kB default), and never letting a net number hide a regression.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ai26_review_delta.py"
sys.path.insert(0, str(ROOT / "tools"))

import ai26_review_delta as delta  # noqa: E402

COLUMNS = ["record_id", "source_url", "platform", "analysis_summary", "formations", "signifiers",
           "nodal_points", "imaginaries", "floating_signifiers", "antagonisms", "equivalences",
           "discourses", "themes", "formation", "text_excerpt"]


def write_export(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            base = {c: "" for c in COLUMNS}
            base.update({"record_id": "r", "source_url": "https://example.invalid/1"})
            base.update(row)
            writer.writerow(base)
    return path


class TestReading:
    def test_a_cell_larger_than_the_csv_default_is_read(self, tmp_path):
        # The real export carries whole source texts; this is the failure that stopped the first pass.
        big = "x" * 200_000
        path = write_export(tmp_path / "big.csv", [{"record_id": "a", "text_excerpt": big}])
        _, rows = delta.read_export(path)
        assert len(rows[0]["text_excerpt"]) == 200_000

    def test_missing_file_and_header_only_file_are_errors(self, tmp_path):
        with pytest.raises(delta.ExportError):
            delta.read_export(tmp_path / "absent.csv")
        header_only = tmp_path / "h.csv"
        header_only.write_text(",".join(COLUMNS) + "\n", encoding="utf-8")
        with pytest.raises(delta.ExportError, match="no records"):
            delta.read_export(header_only)

    def test_a_non_utf8_export_says_so(self, tmp_path):
        path = tmp_path / "latin.csv"
        path.write_bytes(",".join(COLUMNS).encode() + b"\nr1,https://e.invalid/1,,caf\xe9\n")
        with pytest.raises(delta.ExportError, match="UTF-8"):
            delta.read_export(path)


class TestCompare:
    def test_gains_and_regressions_are_separate(self):
        before = [{"record_id": "a", "formations": ""}, {"record_id": "b", "formations": "f"},
                  {"record_id": "c", "formations": "f"}]
        after = [{"record_id": "a", "formations": "f"}, {"record_id": "b", "formations": ""},
                 {"record_id": "c", "formations": "f"}]
        result = delta.compare(before, after)
        formations = result["concepts"]["formations"]
        assert (formations["gained"], formations["lost"], formations["net"]) == (1, 1, 0)
        # A net of zero here would have hidden a regression behind an improvement.
        assert result["regressions_total"] == 1

    def test_ids_on_one_side_only_are_counted_not_scored(self):
        result = delta.compare([{"record_id": "a"}, {"record_id": "b"}], [{"record_id": "b"}, {"record_id": "c"}])
        assert result["shared_record_ids"] == 1
        assert (result["only_before"], result["only_after"]) == (1, 1)

    def test_summary_changes_are_counted_across_either_column_name(self):
        result = delta.compare([{"record_id": "a", "summary": "one"}],
                               [{"record_id": "a", "analysis_summary": "two"}])
        assert result["summary_changed"] == 1

    def test_a_column_absent_from_both_exports_is_reported_not_silently_zero(self):
        result = delta.compare([{"record_id": "a"}], [{"record_id": "a"}], columns=("formations",))
        assert result["concepts"]["signifiers"]["absent"] is True
        assert result["concepts"]["formations"]["present_before"] == 0

    def test_coverage_is_the_only_claim(self):
        result = delta.compare([{"record_id": "a", "formations": ""}],
                               [{"record_id": "a", "formations": "People vs elites"}])
        assert result["concepts"]["formations"]["gained"] == 1
        assert "accuracy" not in json.dumps(result)


class TestCli:
    def test_cli_compares_two_files_and_writes_json(self, tmp_path):
        before = write_export(tmp_path / "b.csv", [{"record_id": "a", "antagonisms": ""}])
        after = write_export(tmp_path / "a.csv", [{"record_id": "a", "antagonisms": "antagonism: x -> y"}])
        out = tmp_path / "delta.json"
        result = subprocess.run([sys.executable, str(TOOL), "--before", str(before), "--after", str(after),
                                 "--json", str(out)], capture_output=True, text=True, timeout=120)
        assert result.returncode == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["delta"]["concepts"]["antagonisms"]["gained"] == 1
        assert "accuracy is not measured here" in result.stdout.lower()

    def test_fail_on_regression_is_opt_in(self, tmp_path):
        before = write_export(tmp_path / "b.csv", [{"record_id": "a", "formations": "f"}])
        after = write_export(tmp_path / "a.csv", [{"record_id": "a", "formations": ""}])
        plain = subprocess.run([sys.executable, str(TOOL), "--before", str(before), "--after", str(after)],
                               capture_output=True, text=True, timeout=120)
        gated = subprocess.run([sys.executable, str(TOOL), "--before", str(before), "--after", str(after),
                                "--fail-on-regression"], capture_output=True, text=True, timeout=120)
        assert plain.returncode == 0
        assert gated.returncode == 1

    def test_usage_error_on_missing_file(self, tmp_path):
        result = subprocess.run([sys.executable, str(TOOL), "--before", str(tmp_path / "no.csv"),
                                 "--after", str(tmp_path / "no2.csv")],
                                capture_output=True, text=True, timeout=120)
        assert result.returncode == 2
        assert "error:" in result.stderr
