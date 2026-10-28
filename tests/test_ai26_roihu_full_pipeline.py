"""Offline checks for the AI26 Roihu deployment (#390).

The scripts are exercised through their refusal and dry-run paths, because those are the behaviours
that must hold before a GPU hour is spent. Live Roihu execution cannot be verified from a workstation
and is not claimed here.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROIHU = ROOT / "scripts" / "roihu"
INSTALL = ROIHU / "install_ai26.sh"
PREFLIGHT = ROIHU / "preflight_ai26.sh"
PIPELINE = ROIHU / "ai26_full_pipeline.sbatch"


def run(script: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    base = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LACLAUGPT_REPO_ROOT": str(ROOT),
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    base.update(env or {})
    return subprocess.run(["bash", str(script)], capture_output=True, text=True, env=base, timeout=120)


def write_env(tmp_path: Path, mode: int = 0o600, **overrides: str) -> Path:
    values = {
        "LACLAUGPT_RUN_ID": "roihu-test-0001",
        "LACLAUGPT_PRIVATE_CONFIG_DIR": str(tmp_path / "private"),
        "LACLAUGPT_MONGODB_URI": "mongodb://example.invalid",
        "LACLAUGPT_REDIS_URL": "redis://example.invalid:6379/0",
        "LACLAUGPT_S3_ENDPOINT": "https://a3s.fi",
        "LACLAUGPT_S3_BUCKET": "example-bucket",
        "LACLAUGPT_MAX_TASKS": "3",
    }
    values.update(overrides)
    path = tmp_path / "roihu.env"
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
    path.chmod(mode)
    return path


# --- static contract (kept in step with the landed implementation) ------------------------------


def test_scripts_parse():
    for script in (INSTALL, PREFLIGHT, PIPELINE):
        assert script.is_file()
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, f"{script.name}: {result.stderr}"


def test_pipeline_is_bounded_and_never_seeds_production():
    text = PIPELINE.read_text(encoding="utf-8")
    assert "roihu-test-*" in text
    assert "--max-tasks" in text
    assert "--seed-ready" not in text
    assert "LLM_ALLOW_CLOUD_FALLBACK=0" in text
    assert "laclaugpt-analysis-worker" in text


def test_preflight_is_fail_closed_on_frozen_inputs():
    text = PREFLIGHT.read_text(encoding="utf-8")
    assert "roihu-test-*" in text
    assert "config_sha256" in text
    assert "codebook_sha256" in text
    assert "preflight --strict" in text


# --- my additions to the landed script ----------------------------------------------------------


def test_pipeline_records_provenance():
    text = PIPELINE.read_text(encoding="utf-8")
    for field in (
        "git_sha",
        "slurm_job_id",
        "worker_id",
        "ollama_model",
        "elapsed_seconds",
        "worker_exit_status",
        "run_id",
    ):
        assert field in text, f"provenance field missing: {field}"


def test_pipeline_refuses_a_non_test_run_id(tmp_path):
    env_file = write_env(tmp_path, LACLAUGPT_RUN_ID="ai26-production-2026")
    result = run(PIPELINE, {"LACLAUGPT_ENV_FILE": str(env_file)})
    assert result.returncode == 2
    assert "Refusing production/shared run ID" in result.stderr


def test_pipeline_refuses_world_readable_env_file(tmp_path):
    env_file = write_env(tmp_path, mode=0o644)
    result = run(PIPELINE, {"LACLAUGPT_ENV_FILE": str(env_file)})
    assert result.returncode == 2
    assert "permissions" in result.stderr


def test_pipeline_refuses_oversized_task_limit(tmp_path):
    env_file = write_env(tmp_path, LACLAUGPT_MAX_TASKS="500")
    result = run(PIPELINE, {"LACLAUGPT_ENV_FILE": str(env_file)})
    assert result.returncode == 2
    assert "refused" in result.stderr.lower()


def test_dry_run_plans_without_modules_or_services(tmp_path):
    env_file = write_env(tmp_path)
    result = run(PIPELINE, {"LACLAUGPT_ENV_FILE": str(env_file), "AI26_DRY_RUN": "1"})
    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    assert "roihu-test-0001" in result.stdout
    assert "laclaugpt-analysis-worker" in result.stdout
