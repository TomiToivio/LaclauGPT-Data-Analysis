from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from laclaugpt_data_analysis.ep24_roihu import (
    EP24State,
    StageResult,
    load_private_codebooks,
    match_codebook,
    private_paths,
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


def test_sqlite_stage_cache_roundtrip(tmp_path: Path) -> None:
    state = EP24State(tmp_path / "ep24.sqlite3")
    state.upsert(
        "ep24-fi-a",
        "FI",
        "fi",
        "fi.csv",
        2,
        "source-a",
        "legacy-a",
        {"video_id": "a"},
    )
    state.write(StageResult("ep24-fi-a", "analysis", "fp-a", "ok", {"demands": ["x"]}))
    assert state.cached("ep24-fi-a", "analysis", "fp-a") == {"demands": ["x"]}
    assert state.cached("ep24-fi-a", "analysis", "fp-b") is None
    with sqlite3.connect(state.path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"records", "stages", "failures", "run_metadata"} <= tables


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
            "id": "fi1",
            "kind": "entity",
            "label": "Vihreät",
            "aliases": ["vihreiden"],
            "country": "FI",
            "status": "researcher-grounded",
            "provenance": "synthetic",
        },
        {
            "id": "pl1",
            "kind": "entity",
            "label": "Koalicja Obywatelska",
            "aliases": ["KO"],
            "country": "PL",
            "status": "researcher-grounded",
            "provenance": "synthetic",
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
    paths = private_paths(root)
    with pytest.raises(ValueError, match="Ambiguous EP24 codebook aliases"):
        load_private_codebooks(paths)


def test_stable_json_is_deterministic() -> None:
    assert stable_json({"b": 2, "a": 1}) == stable_json({"a": 1, "b": 2})


def test_phase0_requirements_stay_free_of_ep24_roihu_dependencies() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "laclaugpt" / "requirements.txt").read_text(encoding="utf-8").casefold()
    for forbidden in ("pandas", "openpyxl", "pyyaml"):
        assert forbidden not in text
