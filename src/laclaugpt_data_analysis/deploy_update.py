"""Fast-forward a deployed checkout when that is provably safe (#564).

The AI26 runner used to reject every cycle whose checkout was not exactly at
``origin/main``. On a repository where several agents push to ``main``, a checkout is
behind within the hour, so ordinary drift became a full stall: two rejected cycles, an
alert, and no analysis until somebody fast-forwarded between cron slots (#554 made the
stall loud; it did not give the runner a way to clear it).

Option 2 from that issue — run the older tree and record it — contradicts the rule this
deployment is built on: the checkout *is* the runtime, and merged fixes are not in effect
until it is refreshed. So this module does the human's ``git merge --ff-only origin/main``
deterministically, and only when nothing can be lost:

* the branch is the expected one (``main``);
* the working tree is clean;
* there are no local commits ahead of the remote;
* no run holds the wrapper's lock (a live cycle must not have files changed under it).

Anything else is refused with a reason, and the caller's existing strict deployment gate
reports it. A refusal here is never silent: the reason is printed and returned.
"""

from __future__ import annotations

import argparse
import fcntl
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = ["UpdateDecision", "fast_forward_checkout"]

#: Reasons, in the order they are checked.
CURRENT = "current"
UPDATED = "fast-forwarded"
DIRTY = "dirty-tree"
AHEAD = "commits-ahead"
WRONG_BRANCH = "wrong-branch"
LOCKED = "lock-held"
NOT_A_REPO = "not-a-git-checkout"
FF_FAILED = "fast-forward-failed"


@dataclass(frozen=True)
class UpdateDecision:
    """What was decided, and why. ``reason`` is stable enough to log and to test."""

    reason: str
    updated: bool
    before: str
    after: str
    behind: int = 0
    ahead: int = 0

    @property
    def ok(self) -> bool:
        return self.reason in (CURRENT, UPDATED)

    def describe(self) -> str:
        detail = f"head={self.before}"
        if self.updated:
            detail = f"{self.before}->{self.after}"
        counts = f" behind={self.behind} ahead={self.ahead}" if self.behind or self.ahead else ""
        return f"checkout {self.reason}{counts} {detail}"


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _rev(path: Path, ref: str) -> str:
    result = _git(path, "rev-parse", "--short", ref)
    return result.stdout.strip() if result.returncode == 0 else ""


def _lock_is_held(lock_file: Path | None) -> bool:
    """True when another process holds the wrapper's flock."""
    if lock_file is None:
        return False
    if not lock_file.exists():
        return False
    try:
        with lock_file.open("a+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError:
        # An unreadable lock file must not be read as "free": refuse the update instead.
        return True
    return False


def fast_forward_checkout(
    path: str | Path,
    *,
    expected_branch: str = "main",
    lock_file: str | Path | None = None,
    fetch: bool = True,
) -> UpdateDecision:
    """Fast-forward ``path`` to ``origin/<expected_branch>`` if nothing can be lost."""
    root = Path(path)
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        return UpdateDecision(NOT_A_REPO, False, "", "")

    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != expected_branch:
        return UpdateDecision(WRONG_BRANCH, False, _rev(root, "HEAD"), "")

    if _git(root, "status", "--porcelain").stdout.strip():
        return UpdateDecision(DIRTY, False, _rev(root, "HEAD"), "")

    if fetch:
        # Best effort: a cron host without network still gets the last known origin/main,
        # which is what the strict gate would have compared against anyway.
        _git(root, "fetch", "--quiet", "origin", expected_branch)

    remote_ref = f"origin/{expected_branch}"
    if _rev(root, remote_ref) == "":
        return UpdateDecision(NOT_A_REPO, False, _rev(root, "HEAD"), "")

    counts = _git(root, "rev-list", "--left-right", "--count", f"HEAD...{remote_ref}")
    if counts.returncode != 0:
        return UpdateDecision(NOT_A_REPO, False, _rev(root, "HEAD"), "")
    # `--left-right` prints the left side first: commits only in HEAD (ahead), then commits
    # only in the remote (behind).
    ahead_text, _, behind_text = counts.stdout.strip().partition("\t")
    ahead = int(ahead_text or 0)
    behind = int(behind_text or 0)
    before = _rev(root, "HEAD")

    if ahead:
        return UpdateDecision(AHEAD, False, before, before, behind, ahead)
    if behind == 0:
        return UpdateDecision(CURRENT, False, before, before, behind, ahead)

    if _lock_is_held(Path(lock_file) if lock_file else None):
        # A running cycle must not have the tree changed under it; the next tick will see
        # the same drift and update once the lock is free.
        return UpdateDecision(LOCKED, False, before, before, behind, ahead)

    merged = _git(root, "merge", "--ff-only", remote_ref)
    if merged.returncode != 0:
        tail = (merged.stderr or merged.stdout).strip().splitlines()[-1:] or [""]
        return UpdateDecision(f"{FF_FAILED}: {tail[0]}", False, before, before, behind, ahead)

    return UpdateDecision(UPDATED, True, before, _rev(root, "HEAD"), behind, ahead)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fast-forward the AI26 analysis checkout when that is provably safe (#564)"
    )
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--lock-file", type=Path, default=None)
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    decision = fast_forward_checkout(
        args.path,
        expected_branch=args.branch,
        lock_file=args.lock_file,
        fetch=not args.no_fetch,
    )
    if not args.quiet:
        stream = sys.stdout if decision.ok else sys.stderr
        print(f"AI26 checkout update: {decision.describe()}", file=stream)
    # The caller's strict drift gate owns the pass/fail decision. This command only
    # performs a safe update and reports what it did; refusing here is not an error.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
