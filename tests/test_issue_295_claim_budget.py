"""Regression coverage for issue #295.

The AI26 analysis cycle spent its entire ``--max-tasks`` budget ack-ing entries
whose results already existed, so the corpus never advanced while every cron tick
reported success. The queue head can carry a large backlog of such entries: they
were published by an earlier revision and never consumed, and neither re-seeding
nor the #72 paging fix removes them.

These tests model that backlog directly. The existing #72 coverage uses a fresh
queue with only a handful of handoffs, which is exactly why the recurrence was
not caught.
"""
from __future__ import annotations

from typing import Any

from laclaugpt_data_analysis.distributed_worker import (
    _claim_budget,
    _cycle_exit_code,
    run_bounded_cycle,
)


class FakeWorker:
    """Yields a scripted sequence of outcomes, like ``run_once`` would."""

    def __init__(self, outcomes: list[str]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0
        self.last_failure_class: str | None = None
        self.last_quarantined = 0

    def run_once(self, *, reclaim_idle_ms: int | None = None) -> str:
        del reclaim_idle_ms
        self.calls += 1
        if not self._outcomes:
            return "idle"
        outcome = self._outcomes.pop(0)
        if outcome == "idle":
            self._outcomes.clear()
        return outcome


# --------------------------------------------------------------- the defect


def test_duplicates_do_not_consume_the_work_budget() -> None:
    """A backlog of already-done entries must not starve actionable work.

    This is the #295 case: 120 duplicates ahead of real work. With max_tasks=2
    the old loop examined 2 entries, both duplicates, and stopped.
    """
    backlog = ["duplicate"] * 120
    worker = FakeWorker([*backlog, "completed", "completed"])

    counts, _, drained = run_bounded_cycle(worker, work_limit=2, claim_limit=200)

    assert counts["completed"] == 2
    assert counts["duplicate"] == 120
    assert counts["work"] == 2
    assert drained is False


def test_cycle_reaches_actionable_work_behind_a_large_backlog() -> None:
    """Forward progress must happen even when the backlog exceeds max_tasks."""
    worker = FakeWorker(["duplicate"] * 50 + ["completed"])

    counts, _, _ = run_bounded_cycle(worker, work_limit=1, claim_limit=200)

    assert counts["completed"] == 1, "cycle must claim past the backlog"


def test_completed_work_is_bounded_by_max_tasks() -> None:
    """``--max-tasks`` bounds work performed, not entries examined."""
    worker = FakeWorker(["completed"] * 10)

    counts, _, _ = run_bounded_cycle(worker, work_limit=3, claim_limit=200)

    assert counts["completed"] == 3
    assert counts["claims"] == 3


def test_claim_budget_still_bounds_a_pure_backlog() -> None:
    """A cycle must terminate even if every entry is a duplicate."""
    worker = FakeWorker(["duplicate"] * 1000)

    counts, _, drained = run_bounded_cycle(worker, work_limit=5, claim_limit=40)

    assert counts["claims"] == 40
    assert counts["duplicate"] == 40
    assert drained is False


# --------------------------------------------------------------- stall signal


def test_all_duplicate_cycle_is_marked_blocked() -> None:
    """A budget exhausted on duplicates is not reported as a healthy cycle."""
    worker = FakeWorker(["duplicate"] * 300)

    counts, _, _ = run_bounded_cycle(worker, work_limit=5, claim_limit=50)

    assert counts["blocked_by_backlog"] == 1
    assert _cycle_exit_code(counts) == 1


def test_genuinely_drained_queue_is_healthy() -> None:
    """An empty queue is a legitimate success, not a stall."""
    worker = FakeWorker(["duplicate", "idle"])

    counts, _, drained = run_bounded_cycle(worker, work_limit=5, claim_limit=50)

    assert drained is True
    assert "blocked_by_backlog" not in counts
    assert _cycle_exit_code(counts) == 0


def test_cycle_with_completed_work_is_not_flagged() -> None:
    worker = FakeWorker(["duplicate"] * 10 + ["completed"])

    counts, _, _ = run_bounded_cycle(worker, work_limit=5, claim_limit=50)

    assert "blocked_by_backlog" not in counts
    assert _cycle_exit_code(counts) == 0


def test_no_claim_at_all_is_not_flagged() -> None:
    """A cycle that claimed nothing has no backlog to report."""
    worker = FakeWorker(["idle"])

    counts, _, drained = run_bounded_cycle(worker, work_limit=5, claim_limit=50)

    assert counts["idle"] == 1
    assert counts["work"] == 0
    assert drained is True
    assert "blocked_by_backlog" not in counts


# --------------------------------------------------------------- other outcomes


def test_retry_and_dead_letter_count_as_work() -> None:
    """Failed attempts still consumed the work budget, so they bound the cycle."""
    worker = FakeWorker(["retry", "dead-letter", "completed"])

    counts, failure_classes, _ = run_bounded_cycle(worker, work_limit=2, claim_limit=50)

    assert counts["work"] == 2
    assert counts["completed"] == 0
    assert counts["retry"] == 1
    assert counts["dead-letter"] == 1
    # Two failed attempts and no completion must surface as a failure.
    assert _cycle_exit_code(counts) == 1


def test_failure_classes_are_counted() -> None:
    """Failure classes are counted per attempt, like the real worker."""

    class Failing(FakeWorker):
        def run_once(self, *, reclaim_idle_ms: int | None = None) -> str:
            # The real AI26TaskWorker resets last_failure_class at the start of
            # every run_once, so a later idle call must not inherit it.
            self.last_failure_class = None
            outcome = super().run_once(reclaim_idle_ms=reclaim_idle_ms)
            if outcome == "retry":
                self.last_failure_class = "ValidationError"
            return outcome

    worker = Failing(["retry", "retry"])
    _, failure_classes, _ = run_bounded_cycle(worker, work_limit=5, claim_limit=50)

    assert failure_classes == {"ValidationError": 2}


# --------------------------------------------------------------- claim budget


def test_claim_budget_defaults_scale_with_max_tasks() -> None:
    assert _claim_budget(10, None) >= 10
    assert _claim_budget(1, None) >= 1
    # Always bounded, so a cycle can never loop indefinitely.
    assert _claim_budget(10_000, None) <= 5000


def test_explicit_max_claims_wins() -> None:
    assert _claim_budget(10, 7) == 7
    assert _claim_budget(10, 0) == 0


def test_claim_budget_handles_zero_and_negative() -> None:
    assert _claim_budget(0, None) >= 0
    assert _claim_budget(-5, None) >= 0
    assert _claim_budget(5, -1) == 0


# --------------------------------------------------------------- compatibility


def test_exit_code_contract_for_issue_101_is_preserved() -> None:
    """The #101 semantics must not regress while fixing #295."""
    # Idle/all-duplicate with no backlog marker stays a success.
    assert _cycle_exit_code({"completed": 0, "duplicate": 3, "retry": 0, "dead-letter": 0}) == 0
    assert _cycle_exit_code({"completed": 0, "duplicate": 0, "retry": 0, "dead-letter": 0}) == 0
    # Failures still fail.
    assert _cycle_exit_code({"completed": 0, "duplicate": 0, "retry": 1, "dead-letter": 0}) == 1
    assert _cycle_exit_code({"completed": 0, "duplicate": 0, "retry": 0, "dead-letter": 1}) == 1
    assert _cycle_exit_code({"completed": 0, "duplicate": 2, "retry": 1, "dead-letter": 0}) == 1
    # Partial progress is fine.
    assert _cycle_exit_code({"completed": 1, "duplicate": 0, "retry": 1, "dead-letter": 1}) == 0


def test_worker_never_exceeds_work_or_claim_budget() -> None:
    """Property check: both budgets are hard caps regardless of the script."""
    for script in (
        ["duplicate"] * 10,
        ["completed"] * 10,
        ["retry"] * 10,
        ["duplicate", "completed"] * 5,
        [],
    ):
        worker: Any = FakeWorker(script)
        counts, _, _ = run_bounded_cycle(worker, work_limit=3, claim_limit=8)
        assert counts["work"] <= 3, script
        assert counts["claims"] <= 8, script
