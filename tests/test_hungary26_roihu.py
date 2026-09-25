from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from laclaugpt_data_analysis.hungary26 import WorkbookRecord
from laclaugpt_data_analysis.hungary26_roihu import (
    DEFAULT_MODEL,
    Hungary26State,
    StageResult,
    normalize_object_ref,
    ollama_chat,
    runtime_fingerprint,
    select_records,
    stable_json,
)


def record(doc: str, platform: str = "instagram") -> WorkbookRecord:
    return WorkbookRecord(
        document_id=doc,
        media_id=f"media-{doc}",
        platform=platform,
        workbook=f"{platform}.xlsx",
        sheet="Sheet1",
        row_number=2,
        source_url=f"https://example.invalid/{doc}",
        post_id=doc,
        author="fixture",
        author_fullname="Fixture",
        caption="Magyar szöveg",
        created_at="2026-04-01",
        collected_at="2026-04-02",
        media_ref=f"videos/{doc}.mp4",
        exact_fingerprint=f"source-{doc}",
        near_duplicate_key="magyar szöveg",
        raw_fields={"caption": "Magyar szöveg"},
    )


def test_sqlite_schema_and_cache_roundtrip(tmp_path: Path) -> None:
    state = Hungary26State(tmp_path / "hungary.sqlite3")
    item = record("a")
    state.upsert_record(item)
    fp = "abc"
    payload = {"hello": "világ"}

    state.write_stage(StageResult(item.document_id, "download", fp, "ok", payload))

    assert state.cached(item.document_id, "download", fp) == payload
    assert state.cached(item.document_id, "download", "different") is None

    with sqlite3.connect(state.path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"records", "stages", "run_metadata"} <= tables


def test_runtime_fingerprint_changes_when_model_or_codebook_changes() -> None:
    item = record("a")
    base = runtime_fingerprint(
        record=item,
        model=DEFAULT_MODEL,
        prompt_version="v1",
        codebook_hash="book-a",
        config_hash="config-a",
    )
    assert base != runtime_fingerprint(
        record=item,
        model="other",
        prompt_version="v1",
        codebook_hash="book-a",
        config_hash="config-a",
    )
    assert base != runtime_fingerprint(
        record=item,
        model=DEFAULT_MODEL,
        prompt_version="v1",
        codebook_hash="book-b",
        config_hash="config-a",
    )


def test_stage_cache_is_invalidated_by_new_fingerprint(tmp_path: Path) -> None:
    state = Hungary26State(tmp_path / "state.sqlite3")
    item = record("a")
    state.upsert_record(item)
    state.write_stage(StageResult(item.document_id, "download", "old", "ok", {"v": 1}))
    state.write_stage(StageResult(item.document_id, "frames", "old", "ok", {"frames": []}))

    state.write_stage(StageResult(item.document_id, "download", "new", "ok", {"v": 2}))

    assert state.cached(item.document_id, "download", "new") == {"v": 2}
    assert state.cached(item.document_id, "frames", "new") is None


def test_object_ref_normalization() -> None:
    assert normalize_object_ref("s3://bucket/a.mp4", "bucket") == "s3://bucket/a.mp4"
    assert normalize_object_ref("folder/a.mp4", "bucket") == "s3://bucket/folder/a.mp4"
    assert normalize_object_ref("", "bucket") == ""


def test_smoke_selection_is_deterministic_and_cross_platform() -> None:
    rows = [
        record("z", "instagram"),
        record("a", "instagram"),
        record("y", "tiktok"),
        record("b", "tiktok"),
    ]
    selected = select_records(rows, "smoke")
    assert [r.document_id for r in selected] == ["a", "b"]


def test_stable_json_is_deterministic() -> None:
    assert stable_json({"b": 2, "a": 1}) == stable_json({"a": 1, "b": 2})


def test_model_guard_rejects_non_gemma4(monkeypatch) -> None:
    monkeypatch.delenv("LACLAUGPT_HUNGARY26_ALLOW_MODEL_OVERRIDE", raising=False)
    with pytest.raises(ValueError, match="gemma4:12b"):
        ollama_chat(model="gemma3:12b", system="x", user="y")


def test_ollama_chat_passes_real_local_image_path(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"fake-jpeg")
    calls = []

    class FakeOllama:
        @staticmethod
        def chat(**kwargs):
            calls.append(kwargs)
            return {"message": {"content": json.dumps({"ok": True})}}

    import sys
    monkeypatch.setitem(sys.modules, "ollama", FakeOllama)

    raw = ollama_chat(
        model=DEFAULT_MODEL,
        system="system",
        user="user",
        images=[str(image)],
    )

    assert json.loads(raw) == {"ok": True}
    assert calls[0]["model"] == "gemma4:12b"
    assert calls[0]["messages"][1]["images"] == [str(image)]


def test_ollama_chat_rejects_remote_image_reference(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ollama_chat(
            model=DEFAULT_MODEL,
            system="system",
            user="user",
            images=["s3://bucket/frame.jpg"],
        )


def test_phase0_minimal_requirements_do_not_gain_multimodal_stack() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "laclaugpt" / "requirements.txt").read_text(encoding="utf-8").casefold()
    for forbidden in ("opencv", "easyocr", "whisper", "torch", "boto3", "pandas"):
        assert forbidden not in text


def test_roihu_launcher_pins_local_gemma4_and_no_cloud_fallback() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "hungary26" / "hungary26_roihu_test.sbatch").read_text(
        encoding="utf-8"
    )
    assert "#SBATCH --account=project_2009497" in text
    assert "/scratch/project_2009497/LaclauGPT-Data-Analysis" in text
    assert "/scratch/project_2009497/LaclauGPT-Private/analysis/hungary26" in text
    assert "gemma4:12b" in text
    assert "LLM_ALLOW_CLOUD_FALLBACK=0" in text
    assert "module load ffmpeg" in text
    assert "unset PYTHONPATH" in text
    assert "unset PYTHONHOME" in text
    assert "SLURM_JOB_ID % 20000" in text
    assert "laclaugpt_data_analysis.hungary26_roihu" in text
