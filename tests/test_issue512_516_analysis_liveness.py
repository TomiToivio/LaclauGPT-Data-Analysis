"""#512 / #513 / #514 / #515 / #516 — the analysis stage's liveness and telemetry defects.

All five were found by running the pipeline on Laskin on 2026-11-22, and they share a theme:
the stage could not describe its own state truthfully.

* #512 a worker that stopped writing held the lock for 45+ minutes; every later tick exited 3
  and looked like a healthy overlap.
* #513 `--check` left no journal row, because its only writer crashed (see #516).
* #514 nothing escalated when ticks kept failing; a journal nobody reads is not a monitor.
* #515 a completed analysis was discarded with `WriteError`, and the log printed a count.
* #516 the telemetry writer ran on the host's 3.10 and imported `datetime.UTC` (3.11+).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from laclaugpt_data_analysis.ai26_tick_telemetry import (
    append_tick,
    classify,
    escalation,
    streak,
)

ROOT = Path(__file__).resolve().parents[1]
TELEMETRY = ROOT / "src" / "laclaugpt_data_analysis" / "ai26_tick_telemetry.py"
WRAPPER = (ROOT / "scripts" / "run_ai26_laskin.sh").read_text(encoding="utf-8")


def write(tmp_path: Path, *, stage: str = "complete", exit_code: int = 0,
          check_only: bool = False, detail: str = "") -> dict:
    return append_tick(tmp_path / "ticks.jsonl", stage=stage, exit_code=exit_code,
                       check_only=check_only, detail=detail)


# ------------------------------------------------------------------ #516

def test_the_writer_imports_on_python_310():
    """`from datetime import UTC` is 3.11+; the host's python3 is 3.10, so every tick crashed."""
    source = TELEMETRY.read_text(encoding="utf-8")
    imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert not any("UTC" in line for line in imports), "UTC is 3.11+; use timezone.utc"
    assert any("timezone" in line for line in imports)


def test_the_wrapper_runs_the_writer_on_the_venv_interpreter():
    """Bare `python3` is the 3.10 host interpreter -- the same bug by another route."""
    assert '.venv/bin/python' in WRAPPER
    assert 'writer=(python3)' in WRAPPER, "and must still work where no venv exists"


def test_the_warning_is_accurate_and_not_escaped():
    """It printed a literal \\n and claimed failure even when a row was written."""
    assert "WARNING: unable to persist AI26 tick telemetry (no journal row for this tick)" in WRAPPER
    assert "telemetry\\\\n" not in WRAPPER


# ------------------------------------------------------------------ #513

def test_a_check_tick_records_its_own_outcome(tmp_path: Path):
    event = write(tmp_path, stage="check", check_only=True, exit_code=0)
    assert event["outcome"] == "check_ok" and event["check_only"] is True
    assert (tmp_path / "ticks.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_the_check_path_is_covered_by_the_exit_trap():
    """#513's root cause: check was the one stage with no writer that worked."""
    assert 'TICK_STAGE="check"' in WRAPPER
    assert "trap record_tick_on_exit EXIT" in WRAPPER


def test_the_wrapper_has_exactly_one_journal_writer():
    """Two writers meant two rows per rejected tick (found while fixing #512)."""
    assert "tick_status " not in WRAPPER, "the second writer is gone"
    assert WRAPPER.count("ai26-analysis-ticks.jsonl") == 1


# ------------------------------------------------------------------ #514

def test_a_streak_counts_only_unhealthy_ticks():
    events = [{"outcome": "cycle_completed"}, {"outcome": "cycle_failed"}, {"outcome": "stale_lock"}]
    assert streak(events) == (2, 0)


def test_a_verification_tick_does_not_count_as_failure():
    """`check_ok` proves the configuration; it must not extend a failure streak."""
    assert streak([{"outcome": "cycle_completed"}, {"outcome": "check_ok"}]) == (0, 0)


def test_rejections_escalate_sooner_than_skips():
    assert escalation(1, 2, escalate_after=3, reject_after=2).startswith("AI26 analysis preflight rejected")
    assert escalation(3, 0, escalate_after=3, reject_after=2).startswith("AI26 analysis has not completed")
    assert escalation(2, 0, escalate_after=3, reject_after=2) == ""


def test_the_alarm_reaches_stderr_as_well_as_the_journal(tmp_path: Path, capsys):
    for _ in range(2):
        write(tmp_path, stage="preflight", exit_code=2)
    event = write(tmp_path, stage="preflight", exit_code=2)
    assert event["consecutive_unhealthy"] == 3
    assert event["escalation"]
    assert "ALERT:" in capsys.readouterr().err


def test_thresholds_are_operator_settable():
    assert "LACLAUGPT_TICK_ESCALATE_AFTER:-3" in WRAPPER
    assert "LACLAUGPT_TICK_REJECT_AFTER:-2" in WRAPPER


# ------------------------------------------------------------------ #512

def test_a_stale_lock_is_not_reported_as_a_healthy_overlap():
    assert classify("lock", 3, False, "stale_lock") == "stale_lock"
    assert classify("lock", 3, False) == "already_running"
    assert classify("complete", 4, False) == "report_failed"


def test_the_wrapper_says_busy_or_hung_with_evidence():
    assert "LACLAUGPT_STALE_LOCK_MINUTES:-20" in WRAPPER
    assert 'TICK_OUTCOME="stale_lock"' in WRAPPER
    assert "start_heartbeat" in WRAPPER and "stop_heartbeat" in WRAPPER
    assert "pgrep -af laclaugpt-analysis-worker" in WRAPPER, "the alert must say where to look"


def test_the_detail_reaches_the_journal(tmp_path: Path):
    event = write(tmp_path, stage="lock", exit_code=3, detail="stale: no heartbeat for 47m")
    assert event["detail"].startswith("stale: no heartbeat")
    assert len(write(tmp_path, detail="x" * 900)["detail"]) == 400


# ------------------------------------------------------------------ #515

def test_the_worker_keeps_the_failure_message():
    source = (ROOT / "src" / "laclaugpt_data_analysis" / "distributed_worker.py").read_text(encoding="utf-8")
    assert "self.last_failure_message: str | None = None" in source
    assert "self.last_failure_message = f\"{self.last_failure_class}: {exc}\"[:600]" in source


def test_the_cycle_prints_one_message_per_failure_class():
    source = (ROOT / "src" / "laclaugpt_data_analysis" / "distributed_worker.py").read_text(encoding="utf-8")
    assert "if failure_class not in failure_classes:" in source
    assert '"AI26 task failure %s: %s"' in source


def test_the_wrapper_is_still_valid_shell():
    result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "run_ai26_laskin.sh")],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_the_writer_cli_records_a_check_tick(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(TELEMETRY), "--path", str(tmp_path / "t.jsonl"),
         "--stage", "check", "--exit-code", "0", "--check-only"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    row = json.loads((tmp_path / "t.jsonl").read_text(encoding="utf-8").strip())
    assert row["outcome"] == "check_ok"
