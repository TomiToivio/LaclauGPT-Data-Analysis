from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from laclaugpt_data_analysis.ep24_roihu import (
    EP24State,
    StageResult,
    existing_representations,
    load_private_codebooks,
    match_codebook,
    materialize_media,
    private_paths,
    resolve_media_ref,
    select_rows,
    stable_record_id,
    stable_json,
)


def test_stable_record_id_prefers_existing_identity() -> None:
    row = {"video_id": "abc-123", "whisper_transcript": "Hei maailma"}
    left = stable_record_id(row, country="FI", source_name="fi.csv", row_number=2)
    right = stable_record_id(row, country="FI", source_name="different.csv", row_number=99)
    assert left == right
    assert left.startswith("ep24-fi-")


def test_sqlite_phase1_schema_and_cache_roundtrip(tmp_path: Path) -> None:
    state = EP24State(tmp_path / "ep24.sqlite3")
    state.upsert(
        "ep24-fi-a", "FI", "fi", "fi.csv", 2, "source-a", "legacy-a", {"video_id": "a"}
    )
    state.write(StageResult("ep24-fi-a", "analysis", "fp-a", "ok", {"demands": ["x"]}))
    assert state.cached("ep24-fi-a", "analysis", "fp-a") == {"demands": ["x"]}
    assert state.cached("ep24-fi-a", "analysis", "fp-b") is None
    with sqlite3.connect(state.path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "records", "stages", "failures", "run_metadata", "representations", "media_assets",
        "source_units", "alignments", "asr", "ocr", "frames",
        "social_semiotic_preanalysis", "relations", "legacy_annotations",
        "discourse_analysis", "postprocess", "comparative_analysis", "uncertainties",
    } <= tables


def test_stage_cache_invalidates_downstream_on_fingerprint_change(tmp_path: Path) -> None:
    state = EP24State(tmp_path / "state.sqlite3")
    state.upsert("id", "FI", "fi", "fi.csv", 2, "source", "legacy", {})
    state.write(StageResult("id", "media", "old", "ok", {"coverage": "processed"}))
    state.write(StageResult("id", "representations", "old", "ok", {"items": []}))
    state.write(StageResult("id", "media", "new", "ok", {"coverage": "processed"}))
    assert state.cached("id", "representations", "new") is None


def test_selection_balances_countries() -> None:
    fi = [{"id": str(i)} for i in range(5)]
    pl = [{"id": str(i)} for i in range(5)]
    smoke = select_rows(fi, pl, "smoke", 20)
    assert [country for country, _ in smoke] == ["FI", "FI", "PL", "PL"]
    pilot = select_rows(fi, pl, "pilot", 3)
    assert [country for country, _ in pilot].count("FI") == 3
    assert [country for country, _ in pilot].count("PL") == 3


def test_codebook_matching_preserves_diacritics_and_country_scope() -> None:
    entries = [
        {
            "id": "fi1", "kind": "entity", "label": "Vihreät", "aliases": ["vihreiden"],
            "country": "FI", "status": "researcher-grounded", "provenance": "synthetic",
        },
        {
            "id": "pl1", "kind": "entity", "label": "Koalicja Obywatelska", "aliases": ["KO"],
            "country": "PL", "status": "researcher-grounded", "provenance": "synthetic",
        },
    ]
    assert match_codebook("Vihreiden ehdokas", entries, country="FI")[0]["label"] == "Vihreät"
    assert match_codebook("Vihreiden ehdokas", entries, country="PL") == []


def test_codebook_collision_fails_closed(tmp_path: Path) -> None:
    root = tmp_path
    (root / "codebooks").mkdir()
    payloads = {
        "ep24_common_private.json": {"entries": []},
        "ep24_finland_private.json": {
            "entities": [
                {"label": "Actor A", "aliases": ["same"]},
                {"label": "Actor B", "aliases": ["same"]},
            ]
        },
        "ep24_poland_private.json": {"entries": []},
    }
    for name, payload in payloads.items():
        (root / "codebooks" / name).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Ambiguous EP24 codebook aliases"):
        load_private_codebooks(private_paths(root))


def test_stable_json_is_deterministic() -> None:
    assert stable_json({"b": 2, "a": 1}) == stable_json({"a": 1, "b": 2})


def test_local_media_resolution_and_materialization(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture-video")
    root = tmp_path / "runtime"
    paths = private_paths(root)
    paths["media"].mkdir(parents=True)
    row = {"video_path": str(source)}
    assert resolve_media_ref(row, {}) == str(source)
    materialized = materialize_media(
        row=row, record_id="ep24-fi-fixture", paths=paths, config={}
    )
    assert materialized["coverage"] == "processed"
    assert Path(materialized["local_path"]).read_bytes() == b"fixture-video"
    assert materialized["sha256"]


def test_text_only_row_never_fabricates_visual_or_audio_evidence() -> None:
    payload = existing_representations({"caption": "Vain teksti"}, "ep24-fi-text")
    assert [item["type"] for item in payload["items"]] == ["source_text"]
    assert all(item["modality"] == "linguistic" for item in payload["items"])


def test_legacy_ocr_and_asr_are_marked_unverified() -> None:
    payload = existing_representations(
        {"caption": "caption", "ocr_1": "teksti kuvassa", "whisper_transcript": "puhe"},
        "ep24-fi-a",
    )
    derived = [item for item in payload["items"] if item["type"] in {"ocr", "asr"}]
    assert derived
    assert all(item["verification"] == "legacy-derived-not-reverified" for item in derived)


def test_phase0_requirements_stay_free_of_ep24_roihu_dependencies() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "laclaugpt" / "requirements.txt").read_text(encoding="utf-8").casefold()
    for forbidden in ("pandas", "openpyxl", "pyyaml", "faster-whisper"):
        assert forbidden not in text


def test_roihu_launcher_has_multimodal_preflight_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "ep24" / "ep24_roihu_reprocess.sbatch").read_text(encoding="utf-8")
    assert "module load ffmpeg" in text
    assert "LLM_ALLOW_CLOUD_FALLBACK=0" in text
    assert "SLURM_JOB_ID % 20000" in text
    assert "laclaugpt_data_analysis.ep24_roihu" in text
