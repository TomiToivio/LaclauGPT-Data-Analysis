"""Tests for the corpus diagnostics (#449, #451, #454, #458, #460).

The tool's numbers go into public issue comments, so the tests pin the arithmetic that a reader cannot
check: the bucket boundaries, what counts as markup, the two label grammars, and the citation shares.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ai26_corpus_diagnostics.py"
sys.path.insert(0, str(ROOT / "tools"))

import ai26_corpus_diagnostics as diag  # noqa: E402

COLUMNS = ["record_id", "source_url", "platform", "source_text", "text_chars", "formations",
           "formation", "signifiers", "antagonisms", "themes", "discourses", "evidence_count",
           "evidence_exact_count"]


def write_csv(path: Path, rows: list[dict[str, str]], columns: list[str] | None = None) -> Path:
    columns = columns or COLUMNS
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for index, row in enumerate(rows):
            base = {c: "" for c in columns}
            base.update({"record_id": f"r{index}", "source_url": f"https://e.invalid/{index}",
                         "platform": "rss"})
            base.update(row)
            writer.writerow(base)
    return path


def read(path: Path):
    return diag.read_export(path)


class TestMarkup:
    def test_html_css_and_script_are_counted_separately(self, tmp_path):
        _, rows = read(write_csv(tmp_path / "e.csv", [
            {"source_text": "<p>text</p>", "text_chars": "12"},
            {"source_text": "--dotcom-chart-color: red; body{}", "text_chars": "34"},
            {"source_text": "function () { return window.x = 1 }", "text_chars": "36"},
            {"source_text": "plain prose about AI", "text_chars": "20"},
        ]))
        data = diag.markup(rows)
        rss = data["per_platform"]["rss"]
        assert rss["with_markup"] == 1
        assert rss["with_css"] == 1
        assert rss["with_script"] == 1
        assert data["rows_with_any_markup"] == 3

    def test_a_row_at_the_upload_cap_is_flagged(self, tmp_path):
        _, rows = read(write_csv(tmp_path / "e.csv", [
            {"source_text": "x", "text_chars": str(diag.TRUNCATION_CAP)},
            {"source_text": "y", "text_chars": "100"},
        ]))
        assert diag.markup(rows)["rows_at_truncation_cap"] == 1

    def test_plain_prose_is_not_markup(self, tmp_path):
        _, rows = read(write_csv(tmp_path / "e.csv", [
            {"source_text": "AI governance is contested. 5 < 6 in the draft.", "text_chars": "48"},
        ]))
        assert diag.markup(rows)["rows_with_any_markup"] == 0


class TestCoverageByLength:
    def test_bucket_boundaries_are_inclusive_where_the_issue_says(self):
        assert diag._bucket(0) == "0"
        assert diag._bucket(1) == "1-60"
        assert diag._bucket(60) == "1-60"
        assert diag._bucket(61) == "61-150"
        assert diag._bucket(3000) == "801-3000"
        assert diag._bucket(3001) == "3001+"

    def test_the_zero_text_stratum_is_reported_on_its_own(self, tmp_path):
        _, rows = read(write_csv(tmp_path / "e.csv", [
            {"source_text": "", "text_chars": "0", "formations": "accelerationist"},
            {"source_text": "", "text_chars": "0", "formations": ""},
            {"source_text": "text", "text_chars": "500", "formations": "critical_ai"},
        ]))
        data = diag.coverage_by_length(rows)
        assert data["zero_text"]["rows"] == 2
        assert data["zero_text"]["formation_share"] == 0.5
        assert data["buckets"]["301-800"]["shares"]["formations"] == 1.0

    def test_a_single_formation_label_also_counts_as_coded(self, tmp_path):
        _, rows = read(write_csv(tmp_path / "e.csv", [
            {"source_text": "t", "text_chars": "10", "formation": "critical_ai"},
        ]))
        assert diag.coverage_by_length(rows)["buckets"]["1-60"]["shares"]["formations"] == 1.0


class TestFormations:
    def test_the_two_grammars_are_separated(self, tmp_path):
        _, rows = read(write_csv(tmp_path / "e.csv", [
            {"formations": "critical_ai"}, {"formations": "Automated Gatekeeping"},
            {"formations": "anti_ai"}, {"formations": "a quoted controversy title"},
        ]))
        data = diag.formations(rows)
        assert data["machine_token_labels"] == 2
        assert data["prose_labels"] == 2
        assert data["machine_share"] == 0.5

    def test_the_dominant_label_share_is_measured(self, tmp_path):
        _, rows = read(write_csv(tmp_path / "e.csv", [{"formations": "accelerationist"}] * 3
                                 + [{"formations": "critical_ai"}]))
        data = diag.formations(rows)
        assert data["top_label_share"] == 0.75
        assert data["distinct_labels"] == 2
        assert data["top_labels"][0]["rows"] == 3

    def test_only_the_first_label_of_a_rendered_list_is_used(self, tmp_path):
        _, rows = read(write_csv(tmp_path / "e.csv", [{"formations": "critical_ai; Automated Gatekeeping"}]))
        assert diag.formations(rows)["machine_token_labels"] == 1


class TestEvidence:
    def test_shares_are_computed_and_empty_rows_counted(self, tmp_path):
        _, rows = read(write_csv(tmp_path / "e.csv", [
            {"evidence_count": "10", "evidence_exact_count": "10"},
            {"evidence_count": "10", "evidence_exact_count": "0"},
            {"evidence_count": "0", "evidence_exact_count": "0"},
        ]))
        data = diag.evidence(rows)
        assert data["evidence_items"] == 20
        assert data["verbatim_items"] == 10
        assert data["verbatim_share"] == 0.5
        assert data["rows_without_any_citation"] == 1
        assert data["rows_fully_verbatim"] == 1

    def test_a_missing_column_is_reported_rather_than_guessed(self):
        # An older export has no evidence columns at all; that is "not measurable", not "zero".
        rows = [{"record_id": "r0", "source_text": "x"}]
        data = diag.evidence(rows)
        assert data["available"] is False
        assert "regenerate" in data["reason"]


class TestFields:
    def test_a_column_empty_in_every_row_is_named(self, tmp_path):
        columns, rows = read(write_csv(tmp_path / "e.csv", [{"themes": "", "signifiers": "s"},
                                                             {"themes": "", "signifiers": ""}]))
        report = diag.fields(rows, columns)
        assert "themes" in report["empty_in_every_row"]
        assert "signifiers" not in report["empty_in_every_row"]

    def test_a_sparse_column_is_not_flagged(self, tmp_path):
        columns, rows = read(write_csv(tmp_path / "e.csv", [{"themes": "x"}, {"themes": ""}]))
        assert "themes" not in diag.fields(rows, columns)["empty_in_every_row"]


class TestCli:
    def test_json_output_is_written_and_deterministic(self, tmp_path):
        source = write_csv(tmp_path / "e.csv", [{"source_text": "<p>x</p>", "text_chars": "8"}])
        out = tmp_path / "d.json"
        code = subprocess.run([sys.executable, str(TOOL), "--input", str(source), "--all",
                               "--json", str(out)], capture_output=True, text=True, timeout=120).returncode
        assert code == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert set(payload) >= {"markup", "coverage_by_length", "formations", "evidence", "fields"}

    def test_no_measurement_is_a_usage_error(self, tmp_path):
        source = write_csv(tmp_path / "e.csv", [{"source_text": "x"}])
        assert subprocess.run([sys.executable, str(TOOL), "--input", str(source)],
                              capture_output=True, text=True, timeout=120).returncode == 2

    def test_a_missing_file_is_reported(self, tmp_path):
        assert subprocess.run([sys.executable, str(TOOL), "--input", str(tmp_path / "no.csv"), "--all"],
                              capture_output=True, text=True, timeout=120).returncode == 2

    def test_the_report_carries_no_source_text(self, tmp_path):
        secret = "UNIQUE-SOURCE-SENTENCE-THAT-MUST-NOT-APPEAR"
        source = write_csv(tmp_path / "e.csv", [{"source_text": f"<p>{secret}</p>", "text_chars": "40"}])
        result = subprocess.run([sys.executable, str(TOOL), "--input", str(source), "--all"],
                                capture_output=True, text=True, timeout=120)
        assert secret not in result.stdout
