"""Behavioural tests for the Roihu provenance and dry-run path (#390).

The existing deployment tests assert that strings appear in the scripts, which cannot
distinguish a working launcher from one that merely mentions the right words. These run
the actual scripts: the provenance recorder is executed against a temporary checkout and
private config, and the launcher is run in dry-run mode with a fake environment.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROIHU = ROOT / "scripts" / "roihu"
RECORDER = ROIHU / "record_provenance.py"
SBATCH = ROIHU / "ai26_full_pipeline.sbatch"


def _private_dir(tmp_path: Path, run_id: str = "roihu-test-abc123") -> Path:
    """A frozen manifest, hashes included — preflight verifies them and fails closed."""
    import hashlib

    d = tmp_path / "private"
    d.mkdir()
    analysis = '{"stages": ["summary"]}'
    codebook = '{"codes": []}'
    (d / "analysis.json").write_text(analysis)
    (d / "codebook.json").write_text(codebook)
    (d / "run-manifest.json").write_text(json.dumps({
        "project_id": "ai26",
        "run_id": run_id,
        "config_sha256": hashlib.sha256(analysis.encode()).hexdigest(),
        "codebook_sha256": hashlib.sha256(codebook.encode()).hexdigest(),
    }, indent=2))
    return d


def _env(**extra) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "LACLAUGPT_RUN_ID": "roihu-test-abc123",
        "LACLAUGPT_PROJECT_ID": "ai26",
        "LACLAUGPT_MACHINE": "roihu",
        "LACLAUGPT_EXECUTION": "slurm",
        "LACLAUGPT_OLLAMA_MODEL": "gemma4:12b",
        "SLURM_JOB_ID": "4242",
        "SLURM_PARTITION": "gpumedium",
    })
    env.update(extra)
    return env


def test_start_phase_records_the_facts_needed_to_reproduce(tmp_path: Path) -> None:
    out = tmp_path / "provenance.json"
    cfg = _private_dir(tmp_path)
    result = subprocess.run(
        [sys.executable, str(RECORDER), "--phase", "start", "--out", str(out),
         "--root", str(ROOT), "--config-dir", str(cfg)],
        env=_env(), capture_output=True, text=True, check=True,
    )
    doc = json.loads(out.read_text())
    start = doc["start"]
    assert start["run_id"] == "roihu-test-abc123"
    assert start["model"] == "gemma4:12b"
    assert start["slurm"]["slurm_job_id"] == "4242"
    assert start["host"]
    # The frozen configuration is identified by hash, not by path.
    assert start["frozen_config"]["run-manifest.json"]
    assert start["frozen_config"]["codebook.json"]
    assert "provenance start" in result.stdout


def test_end_phase_keeps_the_start_and_adds_status(tmp_path: Path) -> None:
    out = tmp_path / "provenance.json"
    cfg = _private_dir(tmp_path)
    for phase, extra in (("start", []), ("end", ["--status", "1", "--elapsed-seconds", "97"])):
        subprocess.run(
            [sys.executable, str(RECORDER), "--phase", phase, "--out", str(out),
             "--root", str(ROOT), "--config-dir", str(cfg), *extra],
            env=_env(), capture_output=True, text=True, check=True,
        )
    doc = json.loads(out.read_text())
    assert doc["start"]["run_id"] == "roihu-test-abc123", "start must survive the end write"
    assert doc["worker_status"] == "1"
    assert doc["elapsed_seconds"] == 97
    assert doc["end"]["git_sha"] is not None


def test_dirty_checkout_is_recorded_as_dirty(tmp_path: Path) -> None:
    """A run from a modified tree must not claim the commit's behaviour."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.txt").write_text("one")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=repo, check=True)
    (repo / "a.txt").write_text("two")

    out = tmp_path / "p.json"
    subprocess.run([sys.executable, str(RECORDER), "--phase", "start", "--out", str(out),
                    "--root", str(repo)], env=_env(), capture_output=True, text=True, check=True)
    assert json.loads(out.read_text())["start"]["git_sha"].endswith("-dirty")


def test_missing_config_dir_is_refused(tmp_path: Path) -> None:
    out = tmp_path / "p.json"
    result = subprocess.run(
        [sys.executable, str(RECORDER), "--phase", "start", "--out", str(out),
         "--root", str(ROOT), "--config-dir", str(tmp_path / "absent")],
        env=_env(), capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert not out.exists()


@pytest.fixture()
def fake_launcher_env(tmp_path: Path) -> dict[str, str]:
    """A launcher environment with CSC's module system and venv stubbed out.

    The point is to exercise the launcher's own guards, not to pretend a cluster exists:
    `module`, `ollama` and the venv are stubs, everything else is the real script.
    """
    bins = tmp_path / "bin"
    bins.mkdir()
    for name in ("module", "ollama", "srun"):
        stub = bins / name
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    # The project venv is real: the launcher calls `python -m laclaugpt_data_analysis.preflight`
    # and a stub interpreter would test the stub instead of the guard.
    venv = ROOT / ".venv"

    cfg = _private_dir(tmp_path)
    env_file = tmp_path / "roihu.env"
    env_file.write_text(
        f"LACLAUGPT_RUN_ID=roihu-test-abc123\n"
        f"LACLAUGPT_PRIVATE_CONFIG_DIR={cfg}\n"
        f"LACLAUGPT_MONGODB_URI=mongodb://example.invalid\n"
        f"LACLAUGPT_REDIS_URL=redis://example.invalid:6379/0\n"
        f"LACLAUGPT_S3_ENDPOINT=https://example.invalid\n"
        f"LACLAUGPT_S3_BUCKET=example\n"
        f"LACLAUGPT_ROIHU_LOG_DIR={tmp_path}\n"
        f"LACLAUGPT_ROIHU_VENV={venv}\n"
        f"LACLAUGPT_DRY_RUN=1\n"
    )
    env_file.chmod(0o600)
    env = _env(
        LACLAUGPT_ENV_FILE=str(env_file),
        LACLAUGPT_DRY_RUN="1",
        LACLAUGPT_PRIVATE_CONFIG_DIR=str(cfg),
    )
    env["PATH"] = f"{bins}:{env['PATH']}"
    return env


def test_dry_run_stops_before_claiming_any_task(tmp_path: Path, fake_launcher_env) -> None:
    """The launcher must be provable on a host without spending a single task."""
    result = subprocess.run(["bash", str(SBATCH)], env=dict(fake_launcher_env),
                            capture_output=True, text=True, cwd=str(ROOT))
    combined = result.stdout + result.stderr
    assert "DRY RUN" in combined, combined[:800]
    assert "the worker will not start" in combined
    assert "analysis:roihu-test-abc123:tasks" in combined


def test_launcher_refuses_a_non_test_run_id(tmp_path: Path, fake_launcher_env) -> None:
    """Production work must never be claimable from this script.

    The env file is sourced with `set -a`, so it overrides the caller's environment —
    which means the guard has to be tested by changing the file, as an operator would.
    """
    env_file = Path(fake_launcher_env["LACLAUGPT_ENV_FILE"])
    env_file.write_text(
        env_file.read_text().replace("LACLAUGPT_RUN_ID=roihu-test-abc123",
                                     "LACLAUGPT_RUN_ID=ai26-production")
    )
    result = subprocess.run(["bash", str(SBATCH)], env=dict(fake_launcher_env),
                            capture_output=True, text=True, cwd=str(ROOT))
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Refusing production/shared run ID" in combined, combined[:500]


def test_launcher_refuses_when_the_manifest_disagrees_with_the_env(tmp_path: Path, fake_launcher_env) -> None:
    """The sbatch guard and the manifest must not be separable.

    The worker takes its run id from the frozen manifest, not from the environment, so a
    matching env is not enough: if the manifest names another run, the isolation claim is
    false and the run must stop before claiming anything.
    """
    cfg = Path(fake_launcher_env["LACLAUGPT_PRIVATE_CONFIG_DIR"])
    manifest = json.loads((cfg / "run-manifest.json").read_text())
    manifest["run_id"] = "roihu-test-other"
    (cfg / "run-manifest.json").write_text(json.dumps(manifest))
    # Dry run stops before preflight by design, so this test needs the real path.
    env_file = Path(fake_launcher_env["LACLAUGPT_ENV_FILE"])
    env_file.write_text(
        "\n".join(line for line in env_file.read_text().splitlines()
                  if not line.startswith("LACLAUGPT_DRY_RUN"))
    )
    env = dict(fake_launcher_env)
    env["LACLAUGPT_DRY_RUN"] = "0"
    result = subprocess.run(["bash", str(SBATCH)], env=env, capture_output=True, text=True,
                            cwd=str(ROOT))
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Run ID mismatch" in combined, combined[:500]


def test_launcher_has_exactly_one_exit_trap() -> None:
    """Two EXIT traps mean one silently stops running: model cleanup or provenance."""
    text = SBATCH.read_text()
    traps = [line for line in text.splitlines() if line.startswith("trap ")]
    assert len(traps) == 1, traps
    assert "cleanup" in traps[0]
