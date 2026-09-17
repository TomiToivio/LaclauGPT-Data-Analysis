import csv
import json
from pathlib import Path

from laclaugpt_data_analysis.ep24_quality import (
    audit_legacy_csv,
    compare_csvs,
    write_sample_csv,
)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_audit_flags_duplicate_and_interpretation_without_evidence(tmp_path: Path) -> None:
    source = tmp_path / "legacy.csv"
    _write_csv(
        source,
        [
            {
                "country": "Finland",
                "new_id": "a",
                "author_username": "one",
                "source_type": "tiktok",
                "political_preference": "metadata-only",
                "summary_analysis": "summary",
                "entities": "Actor",
                "topics": "Topic",
            },
            {
                "country": "Finland",
                "new_id": "a",
                "author_username": "two",
                "source_type": "instagram",
                "whisper_transcript": "evidence",
            },
            {"country": "Poland", "new_id": "pl-1"},
        ],
    )
    report = audit_legacy_csv(source, "finland")
    assert report["rows"] == 2
    assert report["duplicate_document_id_count"] == 1
    assert report["interpretation_without_basic_evidence_rows"] == 1
    assert report["rows_with_political_preference_and_summary"] == 1


def test_sample_is_deterministic_and_country_scoped(tmp_path: Path) -> None:
    source = tmp_path / "legacy.csv"
    rows = []
    for i in range(8):
        rows.append(
            {
                "country": "Finland",
                "new_id": f"fi-{i}",
                "author_username": f"author-{i % 3}",
                "source_type": "tiktok" if i % 2 else "instagram",
                "political_preference": f"group-{i % 2}",
            }
        )
    rows.append({"country": "Poland", "new_id": "pl-1", "author_username": "pl"})
    _write_csv(source, rows)
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    write_sample_csv(source, "finland", first, 5)
    write_sample_csv(source, "finland", second, 5)
    assert first.read_bytes() == second.read_bytes()
    assert "Poland" not in first.read_text(encoding="utf-8")


def test_compare_reports_traceability_without_claiming_better(tmp_path: Path) -> None:
    old = tmp_path / "old.csv"
    new = tmp_path / "new.csv"
    _write_csv(
        old,
        [{"new_id": "a", "summary_analysis": "old", "entities": "A"}],
    )
    _write_csv(
        new,
        [
            {
                "new_id": "a",
                "summary_analysis": "new",
                "entities": "A;B",
                "canonical_json": json.dumps({"id": "a"}),
                "evidence_json": "[]",
                "uncertainty_json": "[]",
                "abstentions_json": "[]",
            }
        ],
    )
    report = compare_csvs(old, new)
    assert report["shared_records"] == 1
    assert report["field_comparison"]["summary_analysis"]["changed_on_shared_records"] == 1
    assert report["new_provenance_coverage"]["canonical_json"] == 1
    assert any("not automatically improved" in note for note in report["interpretation"])
