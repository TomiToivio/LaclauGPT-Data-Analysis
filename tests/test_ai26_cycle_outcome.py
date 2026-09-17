"""Regression coverage for the AI26 cycle exit-status fix (issue #101).

A cycle that attempted work and completed none of it must report failure; an
idle or all-duplicate cycle is a legitimate success.
"""
from __future__ import annotations

from laclaugpt_data_analysis.distributed_worker import _cycle_exit_status


def test_all_duplicate_cycle_is_success() -> None:
    """Nothing new to do is not a failure."""
    assert _cycle_exit_status(attempted=3, completed=0, duplicate=3) == 0


def test_idle_cycle_is_success() -> None:
    assert _cycle_exit_status(attempted=0, completed=0) == 0


def test_cycle_with_completions_is_success() -> None:
    assert _cycle_exit_status(attempted=2, completed=2) == 0


def test_partial_progress_is_success() -> None:
    """Some completions are enough; a partial cycle is not a broken cycle."""
    assert _cycle_exit_status(attempted=3, completed=1, retry=1, dead_letter=1) == 0


def test_all_failed_cycle_reports_failure() -> None:
    """Every attempt failed -> the scheduler must see it."""
    assert _cycle_exit_status(attempted=2, completed=0, retry=1, dead_letter=1) == 1


def test_retry_only_cycle_reports_failure() -> None:
    assert _cycle_exit_status(attempted=1, completed=0, retry=1) == 1


def test_dead_letter_only_cycle_reports_failure() -> None:
    assert _cycle_exit_status(attempted=1, completed=0, dead_letter=1) == 1


def test_mixed_duplicate_and_failure_still_reports_failure() -> None:
    """A duplicate here and there must not mask a genuinely failing task."""
    assert _cycle_exit_status(attempted=2, completed=0, duplicate=1, retry=1) == 1
