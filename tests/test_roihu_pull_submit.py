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


def test_canonical_launchers_stage_missing_private_inputs_without_overwriting_present_inputs():
    ep = (ROOT / "scripts/ep24/ep24_roihu_reprocess.sbatch").read_text()
    hu = (ROOT / "scripts/hungary26/hungary26_roihu_test.sbatch").read_text()
    assert "migrate_from_legacy.sh" in ep
    assert "git submodule update --init --recursive" in ep
    assert "migrate_from_legacy.py" in hu
    assert "build_runtime.py" in hu
    assert "git submodule update --init --recursive" in hu
    assert "hungrary2026" in hu
