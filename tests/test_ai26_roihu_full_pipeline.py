"""Offline checks for the AI26 Roihu full-pipeline deployment (#390).

Nothing here needs CSC: the scripts are executed with dry-run/refusal paths, which is exactly the
behaviour that must be trustworthy *before* a GPU hour is spent. Live Roihu execution cannot be
verified from a workstation and is not claimed.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

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
    return subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, env=base, timeout=120
    )


def write_env(tmp_path: Path, **overrides: str) -> Path:
    values = {
        "LACLAUGPT_RUN_ID": "test-ai26-sample-001",
        "LACLAUGPT_MONGODB_URI": "mongodb://example.invalid",
        "LACLAUGPT_REDIS_URL": "redis://example.invalid:6379/0",
        "LACLAUGPT_S3_ENDPOINT": "https://a3s.fi",
        "LACLAUGPT_S3_BUCKET": "example-bucket",
        "LACLAUGPT_LLM_ENDPOINT": "http://127.0.0.1:11434",
        "LACLAUGPT_PRIVATE_CONFIG_DIR": str(tmp_path / "private"),
    }
    values.update(overrides)
    path = tmp_path / "roihu.env"
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
    return path


# --- static contract ---------------------------------------------------------------------------


def test_scripts_exist_and_parse():
    for script in (INSTALL, PREFLIGHT, PIPELINE):
        assert script.is_file(), script
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, f"{script.name}: {result.stderr}"


def test_install_handles_architecture_and_module_order():
    text = INSTALL.read_text(encoding="utf-8")
    assert "aarch64" in text, "Roihu GH200 is aarch64; the installer must branch on it"
    assert "x86_64" in text, "an x86 mismatch must be reported, not silently accepted"
    # `module purge` removes the compiler and ffmpeg's module needs it.
    assert text.index("gcc ffmpeg") < text.index("ffmpeg -version")
    assert "laclaugpt-preflight" in text


def test_pipeline_uses_documented_roihu_gpu_shape():
    text = PIPELINE.read_text(encoding="utf-8")
    assert "#SBATCH --partition=gpumedium" in text
    assert "#SBATCH --gres=gpu:gh200:" in text
    assert "#SBATCH --time=" in text
    # the canonical worker is the only pipeline entrypoint — no Roihu-only science path
    assert "laclaugpt-analysis-worker" in text
    assert "docs.csc.fi" in text, "resource values must cite where they were verified"


def test_pipeline_records_provenance():
    text = PIPELINE.read_text(encoding="utf-8")
    for field in ("git_sha", "slurm_job_id", "worker_id", "ollama_model", "run_id"):
        assert field in text, field


def test_no_production_identity_is_baked_in():
    for script in (INSTALL, PREFLIGHT, PIPELINE):
        text = script.read_text(encoding="utf-8")
        assert "LACLAUGPT_PRODUCTION_RUN_ID=" not in text, "a production run id must never be committed"


# --- behavioural: refusals and dry run ---------------------------------------------------------


def test_pipeline_refuses_production_run_id(tmp_path):
    env_file = write_env(
        tmp_path,
        LACLAUGPT_RUN_ID="ai26-production-2026",
        LACLAUGPT_PRODUCTION_RUN_ID="ai26-production-2026",
    )
    result = run(PIPELINE, {"AI26_ENV_FILE": str(env_file)})
    assert result.returncode != 0
    assert "must use its own run id" in (result.stderr + result.stdout).lower()


def test_pipeline_refuses_non_test_namespace(tmp_path):
    env_file = write_env(tmp_path, LACLAUGPT_TEST_NAMESPACE="ai26-production")
    result = run(PIPELINE, {"AI26_ENV_FILE": str(env_file)})
    assert result.returncode != 0
    assert "must start with 'test-'" in (result.stderr + result.stdout)


def test_pipeline_requires_a_run_id(tmp_path):
    env_file = write_env(tmp_path, LACLAUGPT_RUN_ID="")
    result = run(PIPELINE, {"AI26_ENV_FILE": str(env_file)})
    assert result.returncode != 0


def test_pipeline_dry_run_plans_without_services(tmp_path):
    env_file = write_env(tmp_path)
    result = run(PIPELINE, {"AI26_ENV_FILE": str(env_file), "AI26_DRY_RUN": "1"})
    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    assert "laclaugpt-analysis-worker" in result.stdout
    assert "test-ai26-sample-001" in result.stdout


def test_preflight_dry_run_passes_without_services():
    result = run(PREFLIGHT, {"AI26_ENV_FILE": "/nonexistent/roihu.env", "AI26_DRY_RUN": "1"})
    assert result.returncode == 0, result.stderr + result.stdout
    assert "preflight: all checks passed" in result.stdout


def test_preflight_fails_without_env_file_when_not_dry():
    result = run(PREFLIGHT, {"AI26_ENV_FILE": "/nonexistent/roihu.env", "AI26_DRY_RUN": "0"})
    assert result.returncode == 1
    assert "env file missing" in result.stdout


def test_preflight_rejects_production_identity(tmp_path):
    env_file = write_env(
        tmp_path,
        LACLAUGPT_PRODUCTION_RUN_ID="test-ai26-sample-001",
    )
    result = run(PREFLIGHT, {"AI26_ENV_FILE": str(env_file), "AI26_DRY_RUN": "1"})
    assert result.returncode == 1
    assert "production run id" in result.stdout.lower()


@pytest.mark.parametrize("key", ["LACLAUGPT_MONGODB_URI", "LACLAUGPT_REDIS_URL", "LACLAUGPT_S3_BUCKET"])
def test_preflight_reports_missing_keys(tmp_path, key):
    # Outside dry run an empty required key must be a failure, not a note.
    env_file = write_env(tmp_path, **{key: ""})
    result = run(PREFLIGHT, {"AI26_ENV_FILE": str(env_file), "AI26_DRY_RUN": "0"})
    assert key in result.stdout
    assert "FAIL" in result.stdout
