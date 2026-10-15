"""Offline acceptance for the bounded, single-owner AI26 run-next entrypoint."""
from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ai26_run_next.sh"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, timeout=10)


def test_default_dry_run_requires_no_runtime_credentials() -> None:
    result = run()
    assert result.returncode == 0
    assert "dry-run" in result.stdout
    assert "max_tasks=10" in result.stdout


def test_bounded_dry_run() -> None:
    result = run("--limit", "003")
    assert result.returncode == 0
    assert "max_tasks=3" in result.stdout


def test_malformed_limits_fail_closed() -> None:
    for value in ("0", "-1", "101", "1.0", "abc", "99999999999999999", "2;echo BAD"):
        result = run("--limit", value)
        assert result.returncode == 2, value
        assert "dry-run" not in result.stdout


def test_unknown_argument_and_missing_limit_fail_closed() -> None:
    assert run("--unknown").returncode == 2
    assert run("--limit").returncode == 2


def test_help_is_read_only() -> None:
    result = run("--help")
    assert result.returncode == 0
    assert "--apply" in result.stdout
