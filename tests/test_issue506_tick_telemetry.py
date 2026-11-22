"""Regression tests for the #506 per-tick operational journal."""
from __future__ import annotations

import json

from laclaugpt_data_analysis.ai26_tick_telemetry import append_tick


def test_all_exit_classes_are_distinct_and_sanitized(tmp_path):
    path = tmp_path / "private" / "ai26-analysis-ticks.jsonl"
    cases = [
        ("preflight", 2, False, "preflight_rejected"),
        ("lock", 3, False, "already_running"),
        ("check", 0, True, "check_ok"),
        ("complete", 0, False, "cycle_completed"),
        # exit 4 is the wrapper's documented report-stage failure: the worker finished, the
        # report did not. Keeping it as cycle_failed hid which half of the cycle broke (#514).
        ("complete", 4, False, "report_failed"),
        ("worker", 124, False, "cycle_failed"),
    ]
    for stage, status, check, expected in cases:
        event = append_tick(path, stage=stage, exit_code=status, check_only=check)
        assert event["outcome"] == expected
        assert event["timestamp_utc"].endswith("+00:00")
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(lines) == len(cases)
    assert [row["outcome"] for row in lines] == [case[3] for case in cases]
    assert "source_text" not in path.read_text()
    assert path.stat().st_mode & 0o077 == 0


def test_completed_tick_reports_explicit_worker_and_report_status(tmp_path):
    event = append_tick(tmp_path / "ticks.jsonl", stage="complete", exit_code=0,
                        check_only=False, worker_status="0", report_status="0", git_sha="abc123")
    assert event["worker_status"] == "0"
    assert event["report_status"] == "0"
    assert event["git_sha"] == "abc123"
