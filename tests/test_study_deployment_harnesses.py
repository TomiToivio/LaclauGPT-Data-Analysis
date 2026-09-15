from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_realtime_worker_preserves_collection_input_and_disables_cloud_fallback() -> None:
    worker = (ROOT / "scripts" / "realtime" / "analyze_jsonl_incremental.py").read_text(
        encoding="utf-8"
    )
    loop = (ROOT / "scripts" / "realtime" / "run_analysis_loop.sh").read_text(
        encoding="utf-8"
    )
    assert "input and output must be different files" in worker
    assert "source_url" in worker
    assert "allow_cloud_fallback=False" in worker
    assert "LLM_ALLOW_CLOUD_FALLBACK=0" in loop


def test_generic_roihu_harness_contains_no_private_project_or_repo_path() -> None:
    text = (ROOT / "scripts" / "reprocessing" / "roihu_study_reprocess.sbatch").read_text(
        encoding="utf-8"
    )
    assert "STUDY_ID" in text
    assert "LACLAUGPT_REPROCESS_DRIVER" in text
    assert "LLM_ALLOW_CLOUD_FALLBACK=0" in text
    assert "project_2009497" not in text
    assert "LaclauGPT-Discourse-Analysis-Private" not in text
    assert "/scratch/" not in text


def test_hungary26_is_documented_as_external_private_runtime() -> None:
    text = (ROOT / "docs" / "study-deployments.md").read_text(encoding="utf-8")
    assert "STUDY_ID=hungary26" in text
    assert "dataset" in text
    assert "remain private" in text
