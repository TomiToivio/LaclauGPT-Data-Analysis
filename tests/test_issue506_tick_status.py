"""#506: a tick that declines to start must not look like a tick that did the work.

Cron saw one exit status and the log saw one line. Three different endings were recorded the same way:

- ``preflight_rejected`` (exit 2) — configuration or checkout state refused the run;
- ``already_running`` (exit 3) — a previous cycle still held the fence;
- ``cycle_failed`` / ``report_failed`` — the work started and did not finish.

The wrapper now appends one JSON record per tick and can summarise the tail, so "three consecutive ticks
analysed nothing" is a query with a threshold, not a reading exercise.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from laclaugpt_data_analysis.tick_status import (
    OUTCOMES,
    append,
    consecutive_non_success,
    summarize,
    tail,
)


def _record(path, outcome, code=0, detail=""):
    return append(path, outcome, code, detail=detail, head="abc1234")


def test_a_record_is_json_with_a_parseable_timestamp(tmp_path):
    path = tmp_path / "ticks.jsonl"
    _record(path, "success")

    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["outcome"] == "success"
    assert row["exit_code"] == 0
    assert row["head"] == "abc1234"
    assert datetime.fromisoformat(row["at"]).tzinfo is not None


def test_an_unknown_outcome_is_refused(tmp_path):
    with pytest.raises(ValueError):
        append(tmp_path / "t.jsonl", "did_something_else", 0)


def test_the_streak_counts_ticks_that_analysed_nothing(tmp_path):
    path = tmp_path / "ticks.jsonl"
    _record(path, "success")
    _record(path, "already_running", 3)
    _record(path, "preflight_rejected", 2)
    _record(path, "already_running", 3)

    rows = tail(path)
    assert consecutive_non_success(rows) == 3


def test_a_success_resets_the_streak(tmp_path):
    path = tmp_path / "ticks.jsonl"
    _record(path, "already_running", 3)
    _record(path, "success")
    _record(path, "already_running", 3)

    assert consecutive_non_success(tail(path)) == 1


def test_the_summary_separates_the_three_endings(tmp_path):
    path = tmp_path / "ticks.jsonl"
    for outcome, code in (("success", 0), ("preflight_rejected", 2), ("already_running", 3)):
        _record(path, outcome, code)

    report = summarize(path, threshold=3)
    assert report["ticks"] == 3
    assert report["counts"] == {"already_running": 1, "preflight_rejected": 1, "success": 1}
    assert report["last"]["outcome"] == "already_running"


def test_the_threshold_exceeded_flag_drives_the_exit_code(tmp_path):
    path = tmp_path / "ticks.jsonl"
    for _ in range(3):
        _record(path, "already_running", 3)

    assert summarize(path, threshold=3)["exceeded"] is True
    assert summarize(path, threshold=4)["exceeded"] is False


def test_a_corrupt_line_is_skipped_rather_than_fatal(tmp_path):
    path = tmp_path / "ticks.jsonl"
    _record(path, "success")
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    _record(path, "already_running", 3)

    rows = tail(path)
    assert [r["outcome"] for r in rows] == ["success", "already_running"]


def test_every_documented_outcome_is_accepted(tmp_path):
    path = tmp_path / "ticks.jsonl"
    for outcome in OUTCOMES:
        _record(path, outcome)
    assert {r["outcome"] for r in tail(path)} == set(OUTCOMES)
