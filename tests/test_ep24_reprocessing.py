from __future__ import annotations

import csv
import json
from pathlib import Path

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.ep24_reprocessing import (
    EP24_LEGACY_COLUMNS,
    load_private_ep24_human_codebook,
    project_ep24_dashboard_row,
    write_ep24_dashboard_csv,
)


def test_private_human_codebook_adapter_keeps_research_content_runtime_only(tmp_path: Path) -> None:
    source = tmp_path / "ep24_fi.json"
    source.write_text(
        json.dumps(
            {
                "country_code": "FI",
                "country": "Finland",
                "entities": [
                    {
                        "label": "Example Actor",
                        "aliases": ["Example Alias"],
                        "type": "person",
                        "provenance": {"workbook": "entities.xlsx", "sheet": "Sheet1", "row": 2},
                    }
                ],
                "themes": [
                    {
                        "label": "Example Theme",
                        "aliases": ["Theme Alias"],
                        "provenance": {"workbook": "themes.xlsx", "sheet": "Sheet1", "row": 3},
                    }
                ],
                "research_notes": [
                    {
                        "text": "Synthetic researcher note",
                        "provenance": {"workbook": "research_notes.xlsx", "sheet": "FI", "row": 4},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    book = load_private_ep24_human_codebook(source)
    assert book.project == "ep24"
    assert {entry.label for entry in book.entries} == {"Example Actor", "Example Theme"}
    assert book.sections["private_runtime"] is True
    assert book.sections["human_research_notes"][0]["text"] == "Synthetic researcher note"
    assert all(entry.metadata.get("private_runtime") for entry in book.entries)


def test_dashboard_projection_preserves_legacy_and_appends_modern_fields(tmp_path: Path) -> None:
    record = CanonicalRecord(
        source_url="https://example.invalid/video/1",
        source_native_ids={"video_id": "vid-1"},
        source={"platform": "TikTok", "author": "example", "language": "fi", "country": "FI"},
        content={"text": "Alkuperäinen puhe", "language": "fi", "translated_text": "Original speech"},
        intermediate={
            "ocr": [{"text": "VISIBLE TEXT", "timestamp_seconds": 0}],
            "frame_analysis": [{"analysis": "Literal visual description", "timestamp_seconds": 0}],
        },
        analysis={
            "status": "analyzed",
            "summary": "Structured analysis",
            "abstentions": ["no_supported_antagonism"],
        },
        human_readable={"summary": "Researcher-readable summary"},
        legacy={"account_type": "Synthetic", "lda_topic": "7"},
    )

    row = project_ep24_dashboard_row(record)
    assert row["account_type"] == "Synthetic"
    assert row["lda_topic"] == "7"
    assert row["video_id"] == "vid-1"
    assert row["ocr_1"] == "VISIBLE TEXT"
    assert row["frame_1"] == "Literal visual description"
    assert row["human_summary"] == "Researcher-readable summary"
    assert "no_supported_antagonism" in row["abstentions_json"]
    assert set(EP24_LEGACY_COLUMNS).issubset(row)

    target = tmp_path / "dashboard.csv"
    write_ep24_dashboard_csv([record], target)
    with target.open(encoding="utf-8", newline="") as handle:
        written = next(csv.DictReader(handle))
    assert written["account_type"] == "Synthetic"
    assert written["canonical_schema_version"] == record.schema_version
    assert json.loads(written["canonical_json"])["source_url"] == record.source_url
