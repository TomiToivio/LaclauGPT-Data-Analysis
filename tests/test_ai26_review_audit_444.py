"""Tests for the AI26 review-export audit (#444).

The tool's output is what a report quotes, so these tests pin the properties a reader relies on:
counts that match the file, a sample that is reproducible and proportional, a before/after that keeps
regressions separate from improvements, and an output that cannot leak private material.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ai26_review_audit.py"
sys.path.insert(0, str(ROOT / "tools"))

import ai26_review_audit as audit  # noqa: E402


def write_export(path: Path, rows: list[dict[str, str]]) -> Path:
    columns = audit.EXPECTED_COLUMNS
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for index, row in enumerate(rows):
            base = {c: "" for c in columns}
            base.update({"record_id": f"r{index:03d}", "source_url": f"https://example.invalid/{index}",
                         "platform": "rss", "language": "en", "text_chars": "100",
                         "text_excerpt": "some text", "analysis_status": "analyzed",
                         "analysis_version": "m1", "summary": f"summary {index}"})
            base.update(row)
            writer.writerow(base)
    return path


class TestProfile:
    def test_counts_match_the_file(self, tmp_path):
        rows = [
            {"formation": "f"}, {"formation": "f"}, {"formation": ""}, {"formation": ""},
        ]
        cols, data = audit.read_export(write_export(tmp_path / "e.csv", rows))
        profile = audit.profile(cols, data)
        assert profile["rows"] == 4
        assert profile["unique_record_ids"] == 4
        assert profile["concept_coverage"]["formations"]["present"] == 2
        assert profile["records_without_formation"] == 2

    def test_duplicate_ids_are_counted_not_collapsed(self, tmp_path):
        cols, data = audit.read_export(write_export(tmp_path / "e.csv", [{"record_id": "same"}, {"record_id": "same"}]))
        profile = audit.profile(cols, data)
        assert profile["rows"] == 2
        assert profile["unique_record_ids"] == 1
        assert profile["duplicate_record_ids"] == 1

    def test_missing_source_text_is_counted_separately_from_missing_output(self, tmp_path):
        rows = [{"text_excerpt": "", "text_chars": "0", "formation": "f"},
                {"text_excerpt": "text", "formation": ""}]
        cols, data = audit.read_export(write_export(tmp_path / "e.csv", rows))
        profile = audit.profile(cols, data)
        assert profile["records_without_source_text"] == 1
        assert profile["records_without_formation"] == 1

    def test_notes_are_collapsed_into_a_taxonomy(self, tmp_path):
        rows = [{"notes": "no stored text"}, {"notes": "no stored text"}, {"notes": "handoff pending; no stored text"}]
        cols, data = audit.read_export(write_export(tmp_path / "e.csv", rows))
        notes = {n["note"]: n["rows"] for n in audit.profile(cols, data)["notes"]}
        assert notes["no stored text"] == 3
        assert notes["handoff pending"] == 1

    def test_repeated_summaries_are_visible(self, tmp_path):
        rows = [{"summary": "Same answer."}, {"summary": "same   answer."}, {"summary": "Different."}]
        cols, data = audit.read_export(write_export(tmp_path / "e.csv", rows))
        rep = audit.profile(cols, data)["summary_repetition"]
        assert rep["summaries"] == 3
        # Case and whitespace differ, so the exact count sees three; normalisation is what exposes
        # the template answer, which is the reason both numbers are reported.
        assert rep["distinct_exact"] == 3
        assert rep["distinct_normalised"] == 2

    def test_schema_drift_is_reported(self):
        diff = audit.schema_diff([c for c in audit.EXPECTED_COLUMNS if c != "antagonisms"] + ["extra"])
        assert diff["missing"] == ["antagonisms"]
        assert diff["unexpected"] == ["extra"]

    def test_an_empty_or_headless_file_is_an_error_not_a_zero_report(self, tmp_path):
        empty = tmp_path / "empty.csv"
        empty.write_text("", encoding="utf-8")
        with pytest.raises(audit.ExportError):
            audit.read_export(empty)
        header_only = tmp_path / "header.csv"
        header_only.write_text(",".join(audit.EXPECTED_COLUMNS) + "\n", encoding="utf-8")
        with pytest.raises(audit.ExportError):
            audit.read_export(header_only)


class TestStratumFloor:
    def test_every_non_empty_stratum_is_represented(self):
        counts = {"big": 5000, "tiny": 2, "small": 8}
        quotas = audit.allocate(counts, 50, floor=1)
        assert sum(quotas.values()) == 50
        assert all(quotas[k] >= 1 for k in counts), quotas

    def test_the_floor_does_not_break_proportionality_for_large_strata(self):
        counts = {"big": 900, "mid": 90, "tiny": 10}
        quotas = audit.allocate(counts, 100, floor=1)
        assert quotas["big"] > quotas["mid"] > quotas["tiny"] >= 1
        assert sum(quotas.values()) == 100

    def test_a_size_smaller_than_the_number_of_strata_takes_the_largest(self):
        quotas = audit.allocate({"a": 100, "b": 50, "c": 2}, 2, floor=1)
        assert sum(quotas.values()) == 2
        assert quotas["a"] == 1 and quotas["b"] == 1 and quotas["c"] == 0

    def test_floor_zero_still_behaves_like_pure_proportionality(self):
        assert audit.allocate({"big": 100, "tiny": 1}, 10, floor=0)["tiny"] == 0

class TestSampling:
    def test_allocation_is_proportional_and_bounded(self):
        quotas = audit.allocate({"a": 80, "b": 15, "c": 5}, 20)
        assert sum(quotas.values()) == 20
        assert quotas["a"] == 16
        assert quotas["c"] >= 1  # the small stratum is not starved out of existence

    def test_allocation_never_exceeds_a_stratum(self):
        quotas = audit.allocate({"a": 2, "b": 1000}, 500)
        assert quotas["a"] <= 2
        assert sum(quotas.values()) == 500

    def test_a_sample_larger_than_the_population_is_capped(self):
        quotas = audit.allocate({"a": 3}, 10)
        assert quotas == {"a": 3}

    def test_the_same_seed_draws_the_same_records_in_any_row_order(self, tmp_path):
        rows = [{"platform": "rss" if i % 2 else "bluesky", "formation": "f" if i % 3 else ""}
                for i in range(40)]
        cols, data = audit.read_export(write_export(tmp_path / "a.csv", rows))
        first = audit.sample(data, 10, seed=7)
        shuffled = list(reversed(data))
        second = audit.sample(shuffled, 10, seed=7)
        assert [r["record_id"] for r in first["rows"]] == [r["record_id"] for r in second["rows"]]

    def test_a_different_seed_draws_a_different_sample(self, tmp_path):
        rows = [{} for _ in range(50)]
        cols, data = audit.read_export(write_export(tmp_path / "a.csv", rows))
        assert ([r["record_id"] for r in audit.sample(data, 10, seed=1)["rows"]]
                != [r["record_id"] for r in audit.sample(data, 10, seed=2)["rows"]])

    def test_strata_cover_text_and_formation_split(self, tmp_path):
        rows = [{"text_excerpt": "t", "formation": ""}, {"text_excerpt": "", "formation": "f"}]
        cols, data = audit.read_export(write_export(tmp_path / "a.csv", rows))
        drawn = audit.sample(data, 2, seed=3)
        assert set(drawn["strata"]) == {"rss|text|no-formation", "rss|no-text|formation"}

    def test_sample_output_carries_no_source_url_unless_asked(self, tmp_path):
        rows = [{"platform": "rss"} for _ in range(5)]
        source = write_export(tmp_path / "e.csv", rows)
        out = tmp_path / "sample.csv"
        code = audit.main(["--input", str(source), "--sample", "3", "--out", str(out)])
        assert code == 0
        header = out.read_text(encoding="utf-8").splitlines()[0]
        assert "source_url" not in header
        assert "record_id" in header

    def test_opt_in_keeps_the_url_for_private_use(self, tmp_path):
        rows = [{} for _ in range(3)]
        source = write_export(tmp_path / "e.csv", rows)
        out = tmp_path / "sample.csv"
        audit.main(["--input", str(source), "--sample", "2", "--out", str(out), "--include-source-url"])
        assert "source_url" in out.read_text(encoding="utf-8").splitlines()[0]


class TestCompare:
    def test_improvements_and_regressions_are_kept_apart(self, tmp_path):
        before = write_export(tmp_path / "before.csv", [
            {"record_id": "a", "formation": "", "signifiers": ""},
            {"record_id": "b", "formation": "f", "signifiers": "s"},
            {"record_id": "c", "formation": "f"},
        ])
        after = write_export(tmp_path / "after.csv", [
            {"record_id": "a", "formation": "f", "signifiers": ""},   # gained a formation
            {"record_id": "b", "formation": "", "signifiers": "s"},   # lost its formation
            {"record_id": "c", "formation": "f", "signifiers": "s"},  # gained signifiers
        ])
        _, b = audit.read_export(before)
        _, a = audit.read_export(after)
        result = audit.compare(b, a)
        assert result["shared_record_ids"] == 3
        assert result["concepts"]["formations"]["gained"] == 1
        assert result["concepts"]["formations"]["lost"] == 1
        assert result["concepts"]["signifiers"]["gained"] == 1
        assert result["regressions_total"] == 1
        assert result["improvements_total"] == 2

    def test_ids_only_in_one_side_are_reported_not_scored(self, tmp_path):
        before = write_export(tmp_path / "before.csv", [{"record_id": "a"}, {"record_id": "b"}])
        after = write_export(tmp_path / "after.csv", [{"record_id": "b"}, {"record_id": "c"}])
        _, b = audit.read_export(before)
        _, a = audit.read_export(after)
        result = audit.compare(b, a)
        assert result["shared_record_ids"] == 1
        assert result["only_before"] == 1
        assert result["only_after"] == 1


class TestCli:
    def test_json_profile_is_published_and_reproducible(self, tmp_path):
        source = write_export(tmp_path / "e.csv", [{"formation": "f"}] * 3 + [{"formation": ""}])
        out = tmp_path / "profile.json"
        code = subprocess.run([sys.executable, str(TOOL), "--input", str(source),
                               "--profile", "--json", str(out)],
                              capture_output=True, text=True, timeout=120).returncode
        assert code == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["profile"]["rows"] == 4
        assert payload["profile"]["concept_coverage"]["formations"]["present"] == 3

    def test_schema_failure_is_a_nonzero_exit(self, tmp_path):
        path = tmp_path / "e.csv"
        path.write_text("record_id,source_url,platform\nr1,u,p\n", encoding="utf-8")
        code = subprocess.run([sys.executable, str(TOOL), "--input", str(path), "--profile",
                               "--fail-on", "schema"],
                              capture_output=True, text=True, timeout=120).returncode
        assert code == 1

    def test_missing_input_is_a_usage_error(self, tmp_path):
        code = subprocess.run([sys.executable, str(TOOL), "--input", str(tmp_path / "nope.csv"),
                               "--profile"], capture_output=True, text=True, timeout=120).returncode
        assert code == 2
