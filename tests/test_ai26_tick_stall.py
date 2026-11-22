"""The AI26 tick journal must announce a stall, not just its individual reasons (#554).

Three defects coincided on Laskin today: a stale checkout made every runnable tick
``preflight_rejected``, an orphaned worker kept the flock so every *other* tick was
``already_running``, and neither streak ever reached its threshold because the two reset
each other. The pipeline was down for hours while each component reported itself fine.

What these tests pin:

* alternating ``already_running`` / ``preflight_rejected`` still reaches an alarm;
* the alarm is a *stall* alarm — "no successful cycle in N ticks" — which is the question an
  operator actually asks, and the only one that is unambiguous when reasons alternate;
* the alert line names the reason mix and the last successful cycle;
* a completed cycle resets the run, and ``check_ok`` is neutral rather than a reset.
"""

from __future__ import annotations

import json
from pathlib import Path

from laclaugpt_data_analysis.ai26_tick_telemetry import append_tick


def write_journal(path: Path, outcomes: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for index, outcome in enumerate(outcomes):
            stream.write(
                json.dumps(
                    {
                        "timestamp_utc": f"2026-11-22T{index:02d}:00:00+00:00",
                        "outcome": outcome,
                        "stage": "lock" if outcome == "already_running" else "preflight",
                        "exit_code": 3 if outcome == "already_running" else 2,
                    }
                )
                + "\n"
            )


def tick(path: Path, outcome: str, **kwargs) -> dict:
    """Append one tick of the given outcome through the real writer."""
    if outcome == "already_running":
        return append_tick(path, stage="lock", exit_code=3, check_only=False, **kwargs)
    if outcome == "preflight_rejected":
        return append_tick(path, stage="preflight", exit_code=2, check_only=False, **kwargs)
    if outcome == "cycle_completed":
        return append_tick(path, stage="complete", exit_code=0, check_only=False, **kwargs)
    if outcome == "check_ok":
        return append_tick(path, stage="check", exit_code=0, check_only=True, **kwargs)
    raise AssertionError(outcome)


def test_alternating_reasons_still_reach_the_stall_alarm(tmp_path: Path, capsys) -> None:
    """The #554 failure: each reason reset the other streak, so no alarm ever fired."""
    journal = tmp_path / "logs" / "ticks.jsonl"
    write_journal(journal, ["cycle_completed", "already_running", "preflight_rejected"])

    event = tick(journal, "already_running", stall_threshold=3)

    assert event["stall_streak"] == 3
    assert event["escalation"] == "stalled"
    alert = capsys.readouterr().err
    assert "ALERT: AI26 analysis is not completing (stalled)" in alert
    assert "already_runningx2" in alert and "preflight_rejectedx1" in alert
    assert "last_success=2026-11-22T00:00:00+00:00" in alert


def test_the_stall_count_ignores_manual_checks(tmp_path: Path) -> None:
    """A `--check` run is not a cycle: it must neither advance nor reset the stall."""
    journal = tmp_path / "ticks.jsonl"
    write_journal(journal, ["cycle_completed", "preflight_rejected", "check_ok"])

    event = tick(journal, "preflight_rejected", stall_threshold=3)

    # One prior reject + this one; the interleaved `check_ok` neither added nor reset anything.
    assert event["stall_streak"] == 2


def test_a_completed_cycle_resets_the_stall(tmp_path: Path) -> None:
    journal = tmp_path / "ticks.jsonl"
    write_journal(journal, ["already_running", "preflight_rejected", "cycle_completed"])

    event = tick(journal, "already_running", stall_threshold=2)

    assert event["stall_streak"] == 1
    assert event["escalation"] is None


def test_below_the_threshold_stays_quiet(tmp_path: Path, capsys) -> None:
    journal = tmp_path / "ticks.jsonl"
    write_journal(journal, ["already_running"])

    event = tick(journal, "preflight_rejected", stall_threshold=3)

    assert event["stall_streak"] == 2
    assert event["escalation"] is None
    assert capsys.readouterr().err == ""


def test_zero_disables_the_stall_alarm(tmp_path: Path, capsys) -> None:
    journal = tmp_path / "ticks.jsonl"
    write_journal(journal, ["already_running"] * 10)

    event = tick(journal, "already_running", stall_threshold=0)

    assert event["escalation"] is None
    assert capsys.readouterr().err == ""


def test_the_individual_streaks_still_count_independently(tmp_path: Path) -> None:
    """The legacy fields keep their meaning: a trailing run of one reason."""
    journal = tmp_path / "ticks.jsonl"
    write_journal(journal, ["preflight_rejected", "already_running", "already_running"])

    event = tick(journal, "already_running")

    assert event["skip_streak"] == 3
    assert event["reject_streak"] == 0
    assert event["stall_reasons"] == {"already_running": 3, "preflight_rejected": 1}


def test_the_status_file_carries_the_stall_fields(tmp_path: Path) -> None:
    journal = tmp_path / "logs" / "ticks.jsonl"
    write_journal(journal, ["preflight_rejected"])

    tick(journal, "preflight_rejected", stall_threshold=2)

    status = json.loads((journal.parent / "ai26-analysis-alert.json").read_text(encoding="utf-8"))
    assert status["escalation"] == "stalled"
    assert status["stall_streak"] == 2
    assert status["stall_reasons"] == {"preflight_rejected": 2}
    assert status["last_success_utc"] is None


def write_progress(path: Path, *, completed: int, duplicate: int) -> None:
    path.write_text(
        json.dumps(
            {
                "timestamp_utc": "2026-11-22T00:30:00+00:00",
                "phase": "cycle_finished",
                "completed": completed,
                "duplicate": duplicate,
                "claims": completed + duplicate + 1,
                "retry": 1,
            }
        ),
        encoding="utf-8",
    )


def test_a_cycle_that_moved_work_is_not_a_stall(tmp_path: Path) -> None:
    """Exit 1 with 3 duplicates and 1 retry is throughput, not a stalled pipeline (#101)."""
    journal = tmp_path / "logs" / "ticks.jsonl"
    write_journal(journal, ["cycle_failed", "cycle_failed"])
    progress = tmp_path / "logs" / "progress.json"
    write_progress(progress, completed=0, duplicate=3)

    event = append_tick(
        journal,
        stage="complete",
        exit_code=1,
        check_only=False,
        stall_threshold=2,
        progress_path=progress,
    )

    assert event["outcome"] == "cycle_failed"
    assert event["stall_streak"] == 0
    assert event["stall_reasons"] == {}
    assert event["escalation"] is None


def test_a_cycle_that_moved_nothing_still_counts(tmp_path: Path) -> None:
    journal = tmp_path / "logs" / "ticks.jsonl"
    write_journal(journal, ["cycle_failed"])
    progress = tmp_path / "logs" / "progress.json"
    write_progress(progress, completed=0, duplicate=0)

    event = append_tick(
        journal,
        stage="complete",
        exit_code=1,
        check_only=False,
        stall_threshold=2,
        progress_path=progress,
    )

    assert event["stall_streak"] == 2
    assert event["escalation"] == "stalled"
