"""Offline safeguards for issue #390 Roihu launcher; no CSC services required."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROIHU = ROOT / "scripts" / "roihu"


def test_roihu_bash_syntax():
    if not shutil.which("bash"):
        return
    for name in ("install_ai26.sh", "preflight_ai26.sh", "ai26_full_pipeline.sbatch"):
        subprocess.run(["bash", "-n", str(ROIHU / name)], check=True)


def test_roihu_bounded_and_isolated_by_default():
    text = (ROIHU / "ai26_full_pipeline.sbatch").read_text()
    assert "roihu-test-*" in text
    assert "--max-tasks" in text
    assert "--seed-ready" not in text.split("# Never seed the production queue.")[1].split("srun --ntasks=1")[1]
    assert "LLM_ALLOW_CLOUD_FALLBACK=0" in text
    assert "LACLAUGPT_MONGODB_URI" in text
    assert "LACLAUGPT_REDIS_URL" in text
    assert "LACLAUGPT_S3_ENDPOINT" in text
    assert "laclaugpt-analysis-worker" in text


def test_roihu_install_uses_local_venv():
    text = (ROIHU / "install_ai26.sh").read_text()
    assert "venv --system-site-packages" in text
    assert "python-pytorch/2.13" in text
    assert "remote,ollama" in text


def test_test_run_preflight_is_fail_closed():
    text = (ROIHU / "preflight_ai26.sh").read_text()
    assert "roihu-test-*" in text
    assert "config_sha256" in text
    assert "codebook_sha256" in text
    assert "preflight --strict" in text


def test_job_local_model_endpoint_is_used_by_canonical_preflight():
    text = (ROIHU / "ai26_full_pipeline.sbatch").read_text()
    assert 'export LACLAUGPT_LLM_ENDPOINT="$OLLAMA_HOST"' in text
    assert 'export LACLAUGPT_LLM_MODEL="$LACLAUGPT_OLLAMA_MODEL"' in text
    assert "export LACLAUGPT_CLOUD_ALLOWED=false" in text
    # rindex, not index: the dry-run block mentions the preflight script before the real
    # call, so the first occurrence is a message, not the execution. Comparing against it
    # made this test fail on a correct launcher.
    real_preflight = text.rindex("bash scripts/roihu/preflight_ai26.sh")
    assert text.index("ollama serve >") < real_preflight
    assert text.index('ollama show "$LACLAUGPT_OLLAMA_MODEL"') < real_preflight
