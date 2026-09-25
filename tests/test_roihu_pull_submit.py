"""Offline deployment contract for the CSC pull-and-sbatch entrypoints.

No private data, Slurm, Allas, or Ollama is needed for these assertions.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_launchers_are_self_discovering():
    for study, script in (
        ("ep24", "scripts/ep24/ep24_roihu_reprocess.sbatch"),
        ("hungary26", "scripts/hungary26/hungary26_roihu_test.sbatch"),
    ):
        body = (ROOT / script).read_text()
        assert "#SBATCH --account=" not in body
        assert "/scratch/" not in body
        assert f"LACLAUGPT_{study.upper()}_PRIVATE_ROOT:?" in body
        assert "SLURM_SUBMIT_DIR" in body
        assert "LACLAUGPT_PRIVATE_REPO" in body
        assert "LLM_ALLOW_CLOUD_FALLBACK=0" in body
        assert "127.0.0.1" in body
        assert "SLURM_JOB_ID" in body
        assert "srun --ntasks=1" in body


def test_canonical_launchers_require_native_private_inputs_without_submodules():
    ep = (ROOT / "scripts/ep24/ep24_roihu_reprocess.sbatch").read_text()
    hu = (ROOT / "scripts/hungary26/hungary26_roihu_test.sbatch").read_text()
    for body in (ep, hu):
        assert "git submodule" not in body
        assert "legacy/LaclauGPT-Discourse-Analysis-Private" not in body
    assert "Missing canonical EP24 input" in ep
    assert "promote_legacy_inputs.sh" in ep
    assert "Missing canonical Hungary26 workbook" in hu
    assert "promote_legacy_inputs.sh" in hu
    assert "build_runtime.py" in hu
