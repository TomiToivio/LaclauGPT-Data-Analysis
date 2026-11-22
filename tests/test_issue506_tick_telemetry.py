"""#506: a tick must leave a machine-readable trace that separates success from skip.

The three hours of silent non-analysis on 2026-11-22 happened because cron saw only an exit
code: a lock-held skip (3), a configuration rejection (2) and a real failure all looked like
"something went wrong", and a healthy tick looked like a healthy tick. The record has to say
which it was, on which commit, and for how many ticks in a row.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from laclaugpt_data_analysis.tick_status import (
    OUTCOMES,
    build_tick,
    consecutive_non_ok,
    escalation,
    record_tick,
)

ROOT = Path(__file__).resolve().parents[1]


def test_a_lock_skip_is_its_own_outcome():
    """#503 gave the skip a distinct exit code; #506 gives it a distinct name."""
    record = build_tick(outcome="lock_held", exit_code=3, deployed_sha="9a08959")
    assert record["outcome"] == "lock_held" and record["exit_code"] == 3
    assert "lock_held" in OUTCOMES and "preflight_rejected" in OUTCOMES


def test_an_unknown_outcome_is_refused():
    """A typo must not invent a fifth state nobody monitors."""
    with pytest.raises(ValueError):
        build_tick(outcome="fine", exit_code=0)


def test_the_record_is_sanitized_and_bounded():
    record = build_tick(outcome="failed", exit_code=1, deployed_sha="a" * 80, detail="x" * 2000)
    assert len(record["deployed_sha"]) == 40
    assert len(record["detail"]) == 400


def test_the_streak_counts_only_trailing_non_ok_ticks():
    history = [{"outcome": "ok"}, {"outcome": "lock_held"}, {"outcome": "lock_held"}]
    assert consecutive_non_ok(history) == 2
    assert consecutive_non_ok([{"outcome": "ok"}]) == 0
    assert consecutive_non_ok([]) == 0


def test_escalation_fires_only_at_the_threshold():
    assert escalation(2, threshold=3) == ""
    assert "3 consecutive ticks" in escalation(3, threshold=3)
    assert escalation(9, threshold=0) == "", "a disabled threshold must stay quiet"


def test_recording_appends_history_and_refreshes_the_last_tick(tmp_path: Path):
    first = record_tick(tmp_path, outcome="lock_held", exit_code=3, deployed_sha="abc1234")
    assert first["consecutive_non_ok"] == 1
    second = record_tick(tmp_path, outcome="lock_held", exit_code=3, deployed_sha="abc1234")
    assert second["consecutive_non_ok"] == 2
    assert (tmp_path / "ticks.jsonl").read_text(encoding="utf-8").count("\n") == 2
    last = json.loads((tmp_path / "last-tick.json").read_text(encoding="utf-8"))
    assert last["outcome"] == "lock_held" and last["consecutive_non_ok"] == 2


def test_a_success_resets_the_streak(tmp_path: Path):
    record_tick(tmp_path, outcome="preflight_rejected", exit_code=2, detail="behind")
    record = record_tick(tmp_path, outcome="ok", exit_code=0)
    assert record["consecutive_non_ok"] == 0
    assert record["escalation"] == ""


def test_the_cli_writes_the_record_and_exits_zero(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, "-m", "laclaugpt_data_analysis.tick_status",
         "--directory", str(tmp_path), "--outcome", "preflight_rejected",
         "--exit-code", "2", "--detail", "deployed revisions failed verification"],
        capture_output=True, text=True, check=False,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["outcome"] == "preflight_rejected" and payload["exit_code"] == 2
    assert (tmp_path / "last-tick.json").is_file()


def test_telemetry_never_decides_the_cycle(tmp_path: Path):
    """A tick directory that cannot be written must not turn a real cycle into a failure."""
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("occupied", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "laclaugpt_data_analysis.tick_status",
         "--directory", str(blocked), "--outcome", "ok", "--exit-code", "0"],
        capture_output=True, text=True, check=False,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0
    assert "telemetry_error" in result.stderr


def test_timestamps_are_utc_aware():
    record = build_tick(outcome="ok", exit_code=0, started_at=datetime(2026, 11, 22, 12, 0, tzinfo=UTC))
    assert record["started_at"].endswith("+00:00")


def test_the_wrapper_records_every_exit_path():
    wrapper = (ROOT / "scripts" / "run_ai26_laskin.sh").read_text(encoding="utf-8")
    assert "record_tick preflight_rejected 2" in wrapper
    assert "record_tick lock_held 3" in wrapper
    assert "record_tick ok 0" in wrapper
    assert "record_tick failed" in wrapper
    assert "TICK_DIR=\"$PRIVATE_ROOT/runtime/ai26/analysis/ticks\"" in wrapper


def test_the_wrapper_is_still_valid_shell():
    result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "run_ai26_laskin.sh")],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
