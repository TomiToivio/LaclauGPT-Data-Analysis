"""Regression coverage for issue #332 — the AI26 cycle must be bounded in TIME.

The reported failure: the bounded analysis cycle acquired its ``flock``, entered
a worker cycle, and stayed there for 6 h+ with the worker ~idle and one task
``pending`` in the consumer group. Every hourly tick in between logged
``already running; exiting cleanly``, so the queue drained nothing.

Root cause, and therefore what these tests pin:

1. ``--max-tasks`` bounds how much WORK is claimed, never how long a cycle may
   take. Nothing bounded the cycle in wall-clock time, so a single blocked task
   held the lock indefinitely.
2. The network clients were built without finite read/socket timeouts. A read
   with no deadline does not raise — it waits — so the retry/dead-letter policy
   never saw an exception to act on.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from laclaugpt_data_analysis import storage

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "run_ai26_laskin.sh"
EXECUTION = ROOT / "config" / "execution" / "laskin-cron.yaml"
DOC = ROOT / "docs" / "AI26_LASKIN_ANALYSIS.md"


def wrapper() -> str:
    return WRAPPER.read_text(encoding="utf-8")


# --------------------------------------------------------------- the ceiling --

def test_the_worker_invocation_is_wrapped_in_a_wall_clock_ceiling() -> None:
    """The core defect: the worker was invoked with nothing bounding its time."""
    script = wrapper()
    assert re.search(r"timeout\s+--signal=TERM\s+--kill-after=", script), (
        "the worker is no longer wrapped in a wall-clock timeout (#332)"
    )
    # The timeout must govern the worker invocation itself, not sit unused.
    timeout_pos = script.index("timeout --signal=TERM")
    worker_pos = script.index("laclaugpt-analysis-worker", timeout_pos)
    assert timeout_pos < worker_pos


def test_the_ceiling_is_configurable_from_the_environment() -> None:
    """An operator must be able to raise it through the private env, not edit code."""
    script = wrapper()
    assert re.search(r"CYCLE_MAX_SECONDS=\$\{LACLAUGPT_CYCLE_MAX_SECONDS:-(\d+)\}", script)
    assert re.search(r"CYCLE_KILL_GRACE_SECONDS=\$\{LACLAUGPT_CYCLE_KILL_GRACE_SECONDS:-(\d+)\}", script)


def test_the_default_ceiling_is_above_the_documented_healthy_band() -> None:
    """A healthy-but-slow cycle must never be truncated.

    The operator guide documents 30-70 min as the normal band. A default at or
    below the top of that band would kill legitimate cycles, so the default must
    exceed it.
    """
    match = re.search(r"CYCLE_MAX_SECONDS=\$\{LACLAUGPT_CYCLE_MAX_SECONDS:-(\d+)\}", wrapper())
    assert match, "the cycle ceiling default is missing"
    default = int(match.group(1))
    assert default > 70 * 60, f"ceiling {default}s is inside the 30-70 min healthy band"


def test_a_timeout_is_distinguishable_from_a_worker_failure() -> None:
    """Monitoring must be able to tell 'hit the ceiling' from 'the task failed'."""
    script = wrapper()
    assert re.search(r'\[\[\s*"\$WORKER_STATUS"\s*-eq\s*124', script)
    assert re.search(r"\$WORKER_STATUS\"\s*-eq\s*137", script)
    assert "CYCLE CEILING exceeded" in script


def test_the_ceiling_is_announced_at_cycle_start() -> None:
    """The active budget must be in the start line, or a stuck cycle is undiagnosable."""
    assert re.search(r"analysis start .*cycle_max_seconds=\$CYCLE_MAX_SECONDS", wrapper())


def test_the_documented_exit_codes_include_the_timeout_codes() -> None:
    """Pin the exit-code row AND its meaning.

    Both weaker forms pass while the fact is gone: a bare ``"124" in text``
    matches prose elsewhere, and a row-shape regex matches a row whose
    description has been gutted. The code must be documented *as the ceiling*.
    """
    text = DOC.read_text(encoding="utf-8")
    assert re.search(r"(?m)^124\s+\S.*ceiling", text), (
        "exit code 124 is no longer documented as the cycle ceiling"
    )
    assert re.search(r"(?m)^137\s+\S", text), "exit code 137 is no longer documented as a row"
    assert "wall-clock ceiling" in text


# ------------------------------------------------------- the network clients --

def test_s3_client_bounds_connect_and_read_timeouts() -> None:
    """The object-store socket was the one actually stuck in CLOSE-WAIT (#332)."""
    source = (ROOT / "src" / "laclaugpt_data_analysis" / "storage.py").read_text(encoding="utf-8")
    assert "connect_timeout=_s3_connect_timeout_seconds()" in source
    assert "read_timeout=_s3_read_timeout_seconds()" in source
    assert '"max_attempts": _s3_max_attempts()' in source


def test_redis_clients_are_built_through_the_bounded_factory() -> None:
    """No Redis client may be constructed without a socket timeout.

    A bare ``redis.Redis.from_url(url)`` anywhere in the runtime reintroduces the
    unbounded read that held the consumer group's message pending for hours.
    The factory itself is the one legitimate construction site.
    """
    factory = ROOT / "src" / "laclaugpt_data_analysis" / "storage.py"
    offenders: list[str] = []
    for path in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "from_url":
                continue
            if not ast.unparse(node.func).endswith("redis.Redis.from_url"):
                continue
            # the bounded factory is the single permitted site
            if path == factory and "socket_timeout=" in ast.unparse(node):
                continue
            offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == [], (
        "unbounded Redis clients (use storage.redis_client instead):\n  " + "\n  ".join(offenders)
    )


def test_the_bounded_redis_factory_sets_both_timeouts() -> None:
    """Both must be BOUND to real values, not merely named.

    Asserting ``"socket_timeout=" in source`` is the recurring-token trap: it
    still passes against ``socket_timeout=None``, i.e. an explicitly disabled
    bound. Pin the assignment to the computed variable.
    """
    source = (ROOT / "src" / "laclaugpt_data_analysis" / "storage.py").read_text(encoding="utf-8")
    assert re.search(r"socket_connect_timeout=connect\b", source), (
        "the Redis connect timeout is no longer bound to a computed value"
    )
    assert re.search(r"socket_timeout=read\b", source), (
        "the Redis read timeout is no longer bound to a computed value"
    )
    # and the computed values must not be None
    assert "socket_timeout=None" not in source
    assert "socket_connect_timeout=None" not in source


# ------------------------------------------------ timeout config never disabled --

@pytest.mark.parametrize(
    "env_name,reader,default",
    [
        ("LACLAUGPT_S3_READ_TIMEOUT_SECONDS", "read", 60.0),
        ("LACLAUGPT_S3_CONNECT_TIMEOUT_SECONDS", "connect", 10.0),
    ],
)
def test_a_zero_or_malformed_timeout_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, env_name: str, reader: str, default: float
) -> None:
    """A timeout of 0 would silently restore the indefinite block.

    A misconfigured private env must not be able to disable the bound, so a
    non-positive or unparsable value falls back to the default.
    """
    fn = {
        "read": storage._s3_read_timeout_seconds,
        "connect": storage._s3_connect_timeout_seconds,
    }[reader]
    for bad in ("0", "-1", "abc", ""):
        monkeypatch.setenv(env_name, bad)
        assert fn() == default, f"{env_name}={bad!r} disabled the bound"


def test_s3_max_attempts_falls_back_when_misconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    for bad in ("0", "-3", "nope", ""):
        monkeypatch.setenv("LACLAUGPT_S3_MAX_ATTEMPTS", bad)
        assert storage._s3_max_attempts() == 3


def test_a_valid_timeout_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LACLAUGPT_S3_READ_TIMEOUT_SECONDS", "12.5")
    assert storage._s3_read_timeout_seconds() == 12.5
    monkeypatch.setenv("LACLAUGPT_S3_MAX_ATTEMPTS", "7")
    assert storage._s3_max_attempts() == 7


def test_the_execution_layer_declares_the_ceiling() -> None:
    """The public execution contract must state the ceiling, not only the wrapper."""
    text = EXECUTION.read_text(encoding="utf-8")
    assert "cycle_max_seconds" in text
    match = re.search(r"cycle_max_seconds:\s*(\d+)", text)
    assert match and int(match.group(1)) > 70 * 60
