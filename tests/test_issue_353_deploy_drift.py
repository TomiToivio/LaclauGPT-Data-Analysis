"""#353: the drift check that makes a stale deployed checkout visible.

On 2026-10-15 Analysis was nine commits behind `main` and three merged fixes were silently not
in effect, so every measurement taken from the live log described pre-fix behaviour. These
tests build real temporary git repositories - a bare "remote" and clones - and pin the
behaviour the wrapper depends on: correct counts, warning-only, never raising.
"""
from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from laclaugpt_data_analysis import deploy_drift


def _git(cwd: pathlib.Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


def _identity(cwd: pathlib.Path) -> None:
    _git(cwd, "config", "user.name", "Synthetic Author")
    _git(cwd, "config", "user.email", "synthetic@example.invalid")


@pytest.fixture()
def repo(tmp_path: pathlib.Path):
    """A bare remote, a clone that tracks it, and a second clone to push through."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")

    clone = tmp_path / "deployed"
    _git(tmp_path, "clone", "--quiet", str(remote), str(clone))
    _identity(clone)
    (clone / "file.txt").write_text("one\n", encoding="utf-8")
    _git(clone, "add", ".")
    _git(clone, "commit", "--quiet", "-m", "first")
    _git(clone, "push", "--quiet", "-u", "origin", "main")

    other = tmp_path / "author"
    _git(tmp_path, "clone", "--quiet", str(remote), str(other))
    _identity(other)
    return {"remote": remote, "clone": clone, "other": other}


def test_a_checkout_in_step_with_its_remote_is_current(repo) -> None:
    report = deploy_drift.checkout_drift(repo["clone"])
    assert report["state"] == deploy_drift.CURRENT
    assert report["behind"] == 0
    assert report["ahead"] == 0
    assert report["branch"] == "main"


def test_a_checkout_behind_its_remote_reports_the_distance(repo) -> None:
    for message in ("second", "third"):
        (repo["other"] / "file.txt").write_text(f"{message}\n", encoding="utf-8")
        _git(repo["other"], "add", ".")
        _git(repo["other"], "commit", "--quiet", "-m", message)
    _git(repo["other"], "push", "--quiet", "origin", "main")

    report = deploy_drift.checkout_drift(repo["clone"])
    assert report["state"] == deploy_drift.BEHIND
    assert report["behind"] == 2
    assert report["ahead"] == 0


def test_a_checkout_ahead_of_its_remote_is_reported_as_ahead(repo) -> None:
    (repo["clone"] / "local.txt").write_text("local\n", encoding="utf-8")
    _git(repo["clone"], "add", ".")
    _git(repo["clone"], "commit", "--quiet", "-m", "local work")

    report = deploy_drift.checkout_drift(repo["clone"])
    assert report["state"] == deploy_drift.AHEAD
    assert report["ahead"] == 1
    assert report["behind"] == 0


def test_divergence_is_named_rather_than_guessed(repo) -> None:
    (repo["other"] / "file.txt").write_text("theirs\n", encoding="utf-8")
    _git(repo["other"], "commit", "--quiet", "-am", "theirs")
    _git(repo["other"], "push", "--quiet", "origin", "main")
    (repo["clone"] / "local.txt").write_text("mine\n", encoding="utf-8")
    _git(repo["clone"], "add", ".")
    _git(repo["clone"], "commit", "--quiet", "-m", "mine")

    report = deploy_drift.checkout_drift(repo["clone"])
    assert report["state"] == deploy_drift.DIVERGED
    assert report["behind"] == 1
    assert report["ahead"] == 1


def test_a_directory_that_is_not_a_repository_is_unknown_not_an_exception(tmp_path) -> None:
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    report = deploy_drift.checkout_drift(plain)
    assert report["state"] == deploy_drift.UNKNOWN
    assert "not a git work tree" in report["detail"]


def test_a_missing_checkout_is_unknown_not_an_exception(tmp_path) -> None:
    report = deploy_drift.checkout_drift(tmp_path / "absent")
    assert report["state"] == deploy_drift.UNKNOWN
    assert report["detail"] == "checkout not found"


def test_offline_mode_still_reports_from_existing_refs(repo) -> None:
    report = deploy_drift.checkout_drift(repo["clone"], fetch=False)
    assert report["state"] == deploy_drift.CURRENT
    assert report["behind"] == 0


def test_sibling_discovery_finds_the_cron_checkouts_beside_it(tmp_path) -> None:
    (tmp_path / "LaclauGPT-Data-Collection").mkdir()
    (tmp_path / "LaclauGPT-Data-Visualization").mkdir()
    (tmp_path / "LaclauGPT-Data-Analysis").mkdir()
    found = {path.name for path in deploy_drift.sibling_checkouts(tmp_path / "LaclauGPT-Data-Analysis")}
    assert found == {"LaclauGPT-Data-Collection", "LaclauGPT-Data-Visualization"}


def test_the_threshold_governs_whether_a_lagging_checkout_is_flagged(repo, capsys) -> None:
    (repo["other"] / "file.txt").write_text("second\n", encoding="utf-8")
    _git(repo["other"], "commit", "--quiet", "-am", "second")
    _git(repo["other"], "push", "--quiet", "origin", "main")

    assert deploy_drift.main(["--path", str(repo["clone"]), "--threshold", "5"]) == 0
    captured = capsys.readouterr()
    assert "WARNING" not in captured.err, "a tolerated lag must not warn"

    assert deploy_drift.main(["--path", str(repo["clone"]), "--threshold", "0"]) == 0
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "may not be in effect" in captured.err


def test_the_check_never_refuses_to_run(repo) -> None:
    """A stale runtime is a risk, not an emergency: exit status stays zero."""
    (repo["other"] / "file.txt").write_text("second\n", encoding="utf-8")
    _git(repo["other"], "commit", "--quiet", "-am", "second")
    _git(repo["other"], "push", "--quiet", "origin", "main")
    assert deploy_drift.main(["--path", str(repo["clone"])]) == 0


def test_json_output_is_machine_readable(repo, capsys) -> None:
    assert deploy_drift.main(["--path", str(repo["clone"]), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["read_only"] is True
    assert payload["checkouts"][0]["name"] == "deployed"
    assert payload["needs_attention"] == []


def test_a_bad_threshold_is_a_usage_error(capsys) -> None:
    assert deploy_drift.main(["--threshold", "-1"]) == 2
    assert "error:" in capsys.readouterr().err


def test_the_cron_wrapper_actually_calls_the_drift_check() -> None:
    """Shipping a module nobody invokes would leave the drift invisible in the hourly log."""
    script = pathlib.Path(deploy_drift.__file__).resolve().parents[2] / "scripts" / "run_ai26_laskin.sh"
    text = script.read_text(encoding="utf-8")
    assert "laclaugpt_data_analysis.deploy_drift" in text
