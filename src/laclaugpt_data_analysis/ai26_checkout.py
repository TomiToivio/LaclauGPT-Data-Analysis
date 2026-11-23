"""Decide whether a behind-only checkout may be fast-forwarded by the AI26 runner (#564).

The analysis gate rejects any checkout that is not exactly ``origin/main``. On a repository where
several agents push, that converts ordinary drift into a stall: two rejections, an ALERT, and no
analysis until a human runs ``git merge --ff-only`` between cron slots. On 2026-11-23 that cost
three cycles.

This module makes that same fast-forward deterministic, and only when it is provably safe:

* the checkout is on the expected branch,
* the working tree is clean (no uncommitted work to lose),
* there are **no** local commits ahead (nothing would be merged, only caught up),
* ``origin/main`` is already fetched (so the refresh cannot invent a new remote state).

Anything else — ahead, diverged, dirty, wrong branch — stays a hard rejection. The point is to
automate the catch-up case, not to weaken the gate.

The caller must hold the AI26 cycle lock: a fast-forward while a cycle runs would swap the code
underneath a live worker.
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path

EXPECTED_BRANCH = "main"
REMOTE_REF = "origin/main"


@dataclass(frozen=True)
class CheckoutState:
    branch: str
    dirty: bool
    ahead: int
    behind: int

    @property
    def clean(self) -> bool:
        return not self.dirty


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=False
    ).stdout.strip()


def inspect_checkout(path: Path) -> CheckoutState:
    """Read the four facts the decision depends on, without changing anything."""
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = bool(_git(path, "status", "--porcelain"))
    counts = _git(path, "rev-list", "--left-right", "--count", f"HEAD...{REMOTE_REF}")
    try:
        ahead, behind = (int(part) for part in counts.split())
    except ValueError:  # the remote ref is not known locally: refuse rather than guess
        ahead, behind = 0, -1
    return CheckoutState(branch=branch, dirty=dirty, ahead=ahead, behind=behind)


def refresh_plan(state: CheckoutState) -> str:
    """Return ``"fast-forward"`` when catching up is safe, otherwise the reason it is not."""
    if state.branch != EXPECTED_BRANCH:
        return f"branch is {state.branch!r}, expected {EXPECTED_BRANCH!r}"
    if not state.clean:
        return "working tree has uncommitted changes"
    if state.behind < 0:
        return f"{REMOTE_REF} is not known locally; fetch before refreshing"
    if state.ahead:
        return f"{state.ahead} local commit(s) ahead of {REMOTE_REF}"
    if state.behind == 0:
        return "already current"
    return "fast-forward"


def fast_forward(path: Path) -> str:
    """Catch the checkout up to ``origin/main``; returns git's summary line."""
    result = subprocess.run(
        ["git", "-C", str(path), "merge", "--ff-only", REMOTE_REF],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "fast-forward failed")
    return (result.stdout.strip().splitlines() or [""])[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fast-forward a behind-only AI26 checkout.")
    parser.add_argument("--path", default=".", help="repository checkout to inspect")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the fast-forward when the plan allows it (default: report only)",
    )
    args = parser.parse_args(argv)

    path = Path(args.path).resolve()
    state = inspect_checkout(path)
    plan = refresh_plan(state)

    if plan != "fast-forward":
        print(f"checkout refresh: {plan} (head={_git(path, 'rev-parse', '--short', 'HEAD')})")
        return 0

    if not args.apply:
        print(f"checkout refresh: would fast-forward {state.behind} commit(s) to {REMOTE_REF}")
        return 0

    before = _git(path, "rev-parse", "--short", "HEAD")
    try:
        summary = fast_forward(path)
    except RuntimeError as exc:
        # The gate will reject the cycle; say why here so the log names the cause.
        print(f"checkout refresh: FAILED {exc}")
        return 3
    after = _git(path, "rev-parse", "--short", "HEAD")
    print(
        f"checkout refresh: fast-forwarded {before} -> {after} ({state.behind} commit(s)); {summary}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
