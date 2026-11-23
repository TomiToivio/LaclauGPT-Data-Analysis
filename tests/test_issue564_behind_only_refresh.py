"""#564: a behind-only checkout refreshes itself, and nothing else does.

The gate stays: wrong branch, dirty tree, local commits ahead, or an unfetched remote all block the
refresh and stay hard rejections. Only the catch-up case — the one a human used to run by hand
between cron slots — is automated.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from laclaugpt_data_analysis.ai26_checkout import (
    CheckoutState,
    inspect_checkout,
    main,
    refresh_plan,
)

REPO = Path(__file__).resolve().parents[1]


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture()
def synced_pair(tmp_path: Path) -> tuple[Path, Path]:
    """An origin with two clones: one to push new commits, one that stays behind."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)

    behind = tmp_path / "behind"
    subprocess.run(["git", "clone", "-q", str(origin), str(behind)], check=True)
    git(
        behind,
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "user.name=t",
        "checkout",
        "-q",
        "-b",
        "main",
    )
    (behind / "file.txt").write_text("one\n")
    git(behind, "add", "file.txt")
    git(
        behind,
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "one",
    )
    git(behind, "push", "-q", "-u", "origin", "main")

    pusher = tmp_path / "pusher"
    subprocess.run(["git", "clone", "-q", str(origin), str(pusher)], check=True)
    # A clone of a bare repo whose HEAD is still master checks out master; track the pushed branch.
    git(pusher, "checkout", "-q", "main")
    (pusher / "file.txt").write_text("one\ntwo\n")
    git(pusher, "add", "file.txt")
    git(
        pusher,
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "two",
    )
    git(pusher, "push", "-q", "origin", "main")

    git(behind, "fetch", "-q", "origin")
    return behind, pusher


def test_safe_case_is_the_only_fast_forward():
    assert refresh_plan(CheckoutState("main", dirty=False, ahead=0, behind=3)) == "fast-forward"


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        (CheckoutState("feature", False, 0, 3), "branch"),
        (CheckoutState("main", True, 0, 3), "uncommitted"),
        (CheckoutState("main", False, 2, 3), "ahead"),
        (CheckoutState("main", False, 0, -1), "not known locally"),
        (CheckoutState("main", False, 0, 0), "already current"),
    ],
)
def test_everything_else_is_refused_with_a_reason(state: CheckoutState, reason: str):
    plan = refresh_plan(state)
    assert plan != "fast-forward"
    assert reason in plan


def test_apply_catches_a_behind_clean_checkout_up(synced_pair, capsys):
    behind, _ = synced_pair
    state = inspect_checkout(behind)
    assert (state.behind, state.ahead, state.dirty) == (1, 0, False)

    before = git(behind, "rev-parse", "HEAD")
    assert main(["--path", str(behind), "--apply"]) == 0
    assert git(behind, "rev-parse", "HEAD") == git(behind, "rev-parse", "origin/main")
    assert git(behind, "rev-parse", "HEAD") != before
    assert "fast-forwarded" in capsys.readouterr().out
    assert (behind / "file.txt").read_text() == "one\ntwo\n"


def test_report_only_does_not_move_the_checkout(synced_pair, capsys):
    behind, _ = synced_pair
    head = git(behind, "rev-parse", "HEAD")

    assert main(["--path", str(behind)]) == 0
    assert git(behind, "rev-parse", "HEAD") == head
    assert "would fast-forward" in capsys.readouterr().out


def test_uncommitted_work_is_never_touched(synced_pair, capsys):
    behind, _ = synced_pair
    (behind / "file.txt").write_text("local edit\n")
    head = git(behind, "rev-parse", "HEAD")

    assert main(["--path", str(behind), "--apply"]) == 0
    assert git(behind, "rev-parse", "HEAD") == head
    assert (behind / "file.txt").read_text() == "local edit\n"
    assert "uncommitted" in capsys.readouterr().out


def test_wrapper_refreshes_under_a_probe_lock_and_keeps_the_gate():
    wrapper = (REPO / "scripts/run_ai26_laskin.sh").read_text()
    assert "try_refresh_when_behind" in wrapper
    # The fast-forward must be probed against the cycle lock, not run blind.
    probe = wrapper.index("try_refresh_when_behind()")
    assert "flock -n 8" in wrapper[probe : probe + 600]
    assert "ai26_checkout --path" in wrapper
    # ...and the strict gate must still run (twice: before and after the refresh attempt).
    assert wrapper.count("deploy_drift --strict --path") == 2
