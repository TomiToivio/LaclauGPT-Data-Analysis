"""#554: a locked tick must not hide a rejection, and the lock must not outlive the wrapper.

The stall this guards against: the checkout drifted 25 commits behind, so preflight rejected every
tick. But a worker started before the drift held the lock, so later ticks recorded
`already_running`, which reset `reject_streak` to 0 — the rejection alert never reached its
threshold, and `escalation` reported "skipped" (the symptom) instead of "rejected" (the cause).
"""

from __future__ import annotations

import json
from pathlib import Path

from laclaugpt_data_analysis.ai26_tick_telemetry import append_tick

REPO = Path(__file__).resolve().parents[1]


def _rows(journal: Path) -> list[dict]:
    return [json.loads(line) for line in journal.read_text().splitlines()]


def test_locked_tick_does_not_clear_a_rejection_streak(tmp_path):
    journal = tmp_path / "ticks.jsonl"
    append_tick(journal, stage="preflight", exit_code=2, check_only=False, reject_threshold=2)
    append_tick(journal, stage="preflight", exit_code=2, check_only=False, reject_threshold=2)
    locked = append_tick(journal, stage="lock", exit_code=3, check_only=False, reject_threshold=2)

    assert locked["outcome"] == "already_running"
    # The lock says nothing about deployability, so the rejection history survives it.
    assert locked["reject_streak"] == 2


def test_rejection_outranks_a_lock_in_the_escalation(tmp_path):
    journal = tmp_path / "ticks.jsonl"
    for _ in range(2):
        append_tick(
            journal,
            stage="preflight",
            exit_code=2,
            check_only=False,
            reject_threshold=2,
            skip_threshold=1,
        )
    event = append_tick(
        journal,
        stage="lock",
        exit_code=3,
        check_only=False,
        reject_threshold=2,
        skip_threshold=1,
    )
    # Both thresholds are exceeded; the actionable cause must be the one reported.
    assert event["skip_streak"] >= 1
    assert event["reject_streak"] >= 2
    assert event["escalation"] == "rejected"


def test_success_still_clears_the_rejection_streak(tmp_path):
    journal = tmp_path / "ticks.jsonl"
    append_tick(journal, stage="preflight", exit_code=2, check_only=False, reject_threshold=2)
    append_tick(journal, stage="complete", exit_code=0, check_only=False, reject_threshold=2)
    fresh = append_tick(
        journal, stage="preflight", exit_code=2, check_only=False, reject_threshold=2
    )
    assert fresh["reject_streak"] == 1


def test_wrapper_does_not_let_the_worker_inherit_the_lock_fd():
    wrapper = (REPO / "scripts/run_ai26_laskin.sh").read_text()
    assert "9>&-" in wrapper, "the worker must not inherit the lock fd (#554)"
    assert "reap_orphaned_worker" in wrapper
    # The reaper runs only after the lock is held: that is what makes the worker an orphan.
    assert wrapper.index("flock -n 9") < wrapper.index("reap_orphaned_worker\n")
