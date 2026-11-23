"""A behind-only checkout is refreshed automatically, and only when nothing can be lost (#564).

The runner used to reject every cycle whose checkout was not exactly at ``origin/main``.
With several agents pushing to ``main``, a checkout is behind within the hour, so ordinary
drift became a stall — two rejected cycles, an alert, and no analysis until somebody ran
``git merge --ff-only`` by hand between cron slots.

These tests build real git repositories and exercise the real decision function:

* a clean, strictly-behind ``main`` is fast-forwarded;
* a dirty tree, a local commit ahead, a wrong branch and a held lock are all refused, and
  refusing leaves HEAD exactly where it was;
* a checkout already at the remote is a no-op;
* the CLI exits 0 when it refuses, because the strict drift gate owns pass/fail.
"""

from __future__ import annotations

import fcntl
import subprocess
import sys
from pathlib import Path

import pytest

from laclaugpt_data_analysis.deploy_update import (
    AHEAD,
    CURRENT,
    DIRTY,
    LOCKED,
    NOT_A_REPO,
    UPDATED,
    WRONG_BRANCH,
    fast_forward_checkout,
)

IDENTITY = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid"]


def git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *IDENTITY, *args], capture_output=True, text=True, check=False
    )


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A bare origin, the deployed checkout, and a second clone that pushes changes."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=main", str(origin)],
        check=True,
        capture_output=True,
    )
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    (work / "file.txt").write_text("one\n", encoding="utf-8")
    git(work, "add", "file.txt")
    git(work, "commit", "-m", "initial")
    git(work, "push", "origin", "main")
    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(origin), str(other)], check=True, capture_output=True)
    return origin, work, other


def advance(other: Path, *, name: str = "file.txt", text: str = "two\n") -> None:
    (other / name).write_text(text, encoding="utf-8")
    git(other, "add", name)
    git(other, "commit", "-m", f"change {name}")
    git(other, "push", "origin", "main")


def head(path: Path) -> str:
    return git(path, "rev-parse", "HEAD").stdout.strip()


def test_a_behind_checkout_is_fast_forwarded(repos: tuple[Path, Path, Path]) -> None:
    _, work, other = repos
    advance(other)
    before = head(work)

    decision = fast_forward_checkout(work, fetch=True)

    assert decision.reason == UPDATED
    assert decision.updated is True and decision.ok
    assert decision.behind == 1 and decision.ahead == 0
    assert head(work) != before
    assert head(work) == git(work, "rev-parse", "origin/main").stdout.strip()
    assert (work / "file.txt").read_text(encoding="utf-8") == "two\n"


def test_a_current_checkout_is_a_no_op(repos: tuple[Path, Path, Path]) -> None:
    _, work, _ = repos
    before = head(work)

    decision = fast_forward_checkout(work)

    assert decision.reason == CURRENT
    assert decision.updated is False
    assert head(work) == before


def test_a_dirty_tree_is_refused_and_left_alone(repos: tuple[Path, Path, Path]) -> None:
    _, work, other = repos
    advance(other)
    before = head(work)
    (work / "file.txt").write_text("uncommitted work\n", encoding="utf-8")

    decision = fast_forward_checkout(work)

    assert decision.reason == DIRTY
    assert head(work) == before
    assert (work / "file.txt").read_text(encoding="utf-8") == "uncommitted work\n"


def test_a_local_commit_ahead_is_refused(repos: tuple[Path, Path, Path]) -> None:
    _, work, other = repos
    advance(other)
    (work / "local.txt").write_text("mine\n", encoding="utf-8")
    git(work, "add", "local.txt")
    git(work, "commit", "-m", "local")
    before = head(work)

    decision = fast_forward_checkout(work)

    assert decision.reason == AHEAD
    assert decision.ahead == 1
    assert head(work) == before


def test_a_wrong_branch_is_refused(repos: tuple[Path, Path, Path]) -> None:
    _, work, other = repos
    advance(other)
    git(work, "checkout", "-b", "fix/some-work")
    before = head(work)

    decision = fast_forward_checkout(work)

    assert decision.reason == WRONG_BRANCH
    assert head(work) == before


def test_a_held_lock_is_refused(repos: tuple[Path, Path, Path], tmp_path: Path) -> None:
    """A running cycle must not have files changed under it."""
    _, work, other = repos
    advance(other)
    before = head(work)
    lock = tmp_path / "run" / "analysis.lock"
    lock.parent.mkdir()
    lock.touch()

    with lock.open("a+") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        decision = fast_forward_checkout(work, lock_file=lock)
        fcntl.flock(holder, fcntl.LOCK_UN)

    assert decision.reason == LOCKED
    assert head(work) == before


def test_a_directory_that_is_not_a_checkout_is_refused(tmp_path: Path) -> None:
    plain = tmp_path / "not-a-repo"
    plain.mkdir()

    assert fast_forward_checkout(plain).reason == NOT_A_REPO


def test_the_cli_does_not_fail_the_tick_when_it_refuses(repos: tuple[Path, Path, Path]) -> None:
    """The strict drift gate owns pass/fail; this command only performs a safe update."""
    _, work, other = repos
    advance(other)
    (work / "file.txt").write_text("uncommitted\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "laclaugpt_data_analysis.deploy_update",
            "--path",
            str(work),
            "--no-fetch",
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        env={
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "PATH": "/usr/bin:/bin",
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert DIRTY in result.stderr
