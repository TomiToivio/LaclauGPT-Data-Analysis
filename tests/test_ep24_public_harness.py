from pathlib import Path


def test_public_ep24_harness_contains_no_private_project_constants() -> None:
    root = Path(__file__).resolve().parents[1]
    batch = (root / "scripts/ep24/ep24_roihu_reprocess.sbatch").read_text(encoding="utf-8")
    runner = (root / "scripts/ep24/run_country_reprocess.sh").read_text(encoding="utf-8")
    text = batch + runner

    assert "project_2009497" not in text
    assert "/scratch/project_" not in text
    assert "LaclauGPT-Discourse-Analysis-Private" not in text
    assert "KEEP_PRIVATE" not in text
    assert "private_only" not in text


def test_public_ep24_harness_requires_private_inputs_at_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    runner = (root / "scripts/ep24/run_country_reprocess.sh").read_text(encoding="utf-8")

    assert "EP24_PIPELINE_SCRIPT" in runner
    assert "EP24_REQUIRE_HUMAN_CODEBOOK=1" in runner
    assert "private_codebooks" in runner
    assert "run_configs" in runner
    assert "LACLAUGPT_DATA_DIR" in runner


def test_roihu_harness_forces_local_llm_mode() -> None:
    root = Path(__file__).resolve().parents[1]
    batch = (root / "scripts/ep24/ep24_roihu_reprocess.sbatch").read_text(encoding="utf-8")

    assert "LLM_MODE=local" in batch
    assert "LLM_ALLOW_CLOUD_FALLBACK=0" in batch
    assert "gemma4:26b" in batch
    assert "translategemma:27b" in batch
