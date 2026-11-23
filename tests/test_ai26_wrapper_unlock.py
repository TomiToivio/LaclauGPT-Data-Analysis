"""A lock left by a killed wrapper must be clearable by one documented command (#554).

On Laskin the wrapper ran the worker under ``timeout``; killing the wrapper killed neither
child, the flock stayed held through the inherited descriptor, and every later tick exited
``already_running``. The only recovery was to find the PIDs with ``fuser`` and kill them by
hand.

These tests exercise the recovery path end to end: the real script, a real lock file, real
processes. No cron, no model, no private runtime.

What they pin:

* nothing to clear is success, not an error;
* a live wrapper is never signalled;
* a live PID that is not an AI26 worker is never signalled;
* a lock that is genuinely held is refused with an actionable message;
* a dead holder's stale pid file is cleaned and the lock reports clear;
* a glob in the lock path is rejected instead of creating a literal ``*.lock`` file.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_ai26_laskin.sh"


def run_force_unlock(tmp_path: Path, lock: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "LACLAUGPT_PRIVATE_ROOT": str(tmp_path),
        "LACLAUGPT_AI26_ANALYSIS_LOCK": str(lock),
    }
    return subprocess.run(
        ["bash", str(SCRIPT), "--force-unlock"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_nothing_to_unlock_is_success(tmp_path: Path) -> None:
    result = run_force_unlock(tmp_path, tmp_path / "run" / "absent.lock")

    assert result.returncode == 0, result.stderr
    assert "nothing to unlock" in result.stdout


def test_a_free_lock_reports_cleared(tmp_path: Path) -> None:
    lock = tmp_path / "run" / "ai26.lock"
    lock.parent.mkdir(parents=True)
    lock.touch()
    (lock.parent / (lock.name + ".pid")).write_text("999999 999998\n", encoding="utf-8")

    result = run_force_unlock(tmp_path, lock)

    assert result.returncode == 0, result.stderr
    assert "lock cleared" in result.stdout
    assert not (lock.parent / (lock.name + ".pid")).exists()


def test_a_live_wrapper_is_never_signalled(tmp_path: Path) -> None:
    lock = tmp_path / "run" / "ai26.lock"
    lock.parent.mkdir(parents=True)
    lock.touch()
    (lock.parent / (lock.name + ".pid")).write_text(f"999999 {os.getpid()}\n", encoding="utf-8")

    result = run_force_unlock(tmp_path, lock)

    assert result.returncode == 2
    assert "wrapper pid" in result.stderr and "is alive" in result.stderr


def test_a_live_non_worker_pid_is_refused(tmp_path: Path) -> None:
    """A pid file is not permission to kill whatever now owns that pid."""
    lock = tmp_path / "run" / "ai26.lock"
    lock.parent.mkdir(parents=True)
    lock.touch()
    (lock.parent / (lock.name + ".pid")).write_text(f"{os.getpid()} 999998\n", encoding="utf-8")

    result = run_force_unlock(tmp_path, lock)

    assert result.returncode == 2
    assert "is not an AI26 worker" in result.stderr


def test_a_held_lock_is_refused_with_a_next_step(tmp_path: Path) -> None:
    lock = tmp_path / "run" / "ai26.lock"
    lock.parent.mkdir(parents=True)
    with lock.open("a+") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        result = run_force_unlock(tmp_path, lock)
        fcntl.flock(holder, fcntl.LOCK_UN)

    assert result.returncode == 2
    assert "still held" in result.stderr
    assert "fuser" in result.stderr


def test_a_glob_in_the_lock_path_is_rejected(tmp_path: Path) -> None:
    """The literal `*.lock` file came from an unexpanded glob; refuse it loudly."""
    lock = tmp_path / "run" / "*.lock"

    result = run_force_unlock(tmp_path, lock)

    assert result.returncode == 2
    assert "shell glob" in result.stderr
    assert not Path(str(lock)).exists()


def test_force_unlock_is_not_recorded_as_a_completed_cycle(tmp_path: Path) -> None:
    """A recovery command must not reset the stall alarm it is recovering from."""
    telemetry = tmp_path / "analysis" / "ai26" / "logs"
    telemetry.mkdir(parents=True)
    journal = telemetry / "ai26-analysis-ticks.jsonl"
    lock = tmp_path / "run" / "ai26.lock"

    result = run_force_unlock(tmp_path, lock)

    assert result.returncode == 0, result.stderr
    assert not journal.exists(), "force-unlock wrote a tick event and masked the stall"
