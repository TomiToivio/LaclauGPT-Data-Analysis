from pathlib import Path


def test_roihu_harness_matches_issue_245_deployment_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    batch = (root / "scripts/ep24/ep24_roihu_reprocess.sbatch").read_text(encoding="utf-8")

    assert "#SBATCH --account=" not in batch
    assert "/scratch/" not in batch
    assert 'LACLAUGPT_EP24_PRIVATE_ROOT:?' in batch
    assert "gemma4:12b" in batch
    assert "LLM_MODE=local" in batch
    assert "LLM_ALLOW_CLOUD_FALLBACK=0" in batch
    assert "SLURM_JOB_ID % 20000" in batch
    assert "unset PYTHONPATH" in batch
    assert "unset PYTHONHOME" in batch
    assert "python -m laclaugpt_data_analysis.ep24_roihu" in batch
    assert "srun --ntasks=1" in batch


def test_roihu_harness_uses_private_canonical_root() -> None:
    root = Path(__file__).resolve().parents[1]
    batch = (root / "scripts/ep24/ep24_roihu_reprocess.sbatch").read_text(encoding="utf-8")

    assert "LACLAUGPT_EP24_PRIVATE_ROOT" in batch
    assert "LaclauGPT-Private/analysis/ep24" in batch
    assert "LaclauGPT-Discourse-Analysis-Private" not in batch
    assert "EP24_PIPELINE_SCRIPT" not in batch
