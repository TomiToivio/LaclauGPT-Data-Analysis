from pathlib import Path


def test_issue99_orchestrator_supports_dry_pilot_full_and_audits() -> None:
    root = Path(__file__).resolve().parents[1]
    runner = (root / "scripts/ep24/run_country_reprocess_v2.sh").read_text(encoding="utf-8")

    assert "EP24_RUN_MODE" in runner
    assert "pilot|full|dry-run" in runner
    assert "ep24_quality audit-legacy" in runner
    assert "ep24_quality sample" in runner
    assert "ep24_quality compare" in runner
    assert "private_pipeline/ep24_mm_pipeline.py" in runner


def test_roihu_batch_uses_issue99_orchestrator() -> None:
    root = Path(__file__).resolve().parents[1]
    batch = (root / "scripts/ep24/ep24_roihu_reprocess.sbatch").read_text(encoding="utf-8")

    assert "run_country_reprocess_v2.sh" in batch
    assert "EP24_RUN_MODE=${EP24_RUN_MODE:-pilot}" in batch
    assert "LLM_ALLOW_CLOUD_FALLBACK=0" in batch


def test_issue99_runbook_points_to_canonical_private_repo() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = (root / "docs/EP24_ISSUE99_ROIHU.md").read_text(encoding="utf-8")

    assert "LaclauGPT-Private/analysis/ep24" in doc
    assert "LaclauGPT-Discourse-Analysis-Private" not in doc
    assert "ep24.frame_analysis:v2" in doc
    assert "EP24_RUN_MODE=full" in doc
