from pathlib import Path

import pytest

from laclaugpt_data_analysis.codebooks import Codebook, CodebookEntry
from laclaugpt_data_analysis.hungary26 import (
    WorkbookRecord,
    audit_records,
    codebook_collisions,
    deterministic_pilot,
    private_runtime_preflight,
)


def record(doc: str, platform: str, *, caption: str = "Magyar szöveg", media: str = "v.mp4") -> WorkbookRecord:
    return WorkbookRecord(
        document_id=doc,
        media_id=f"media-{doc}",
        platform=platform,
        workbook=f"{platform}.xlsx",
        sheet="Sheet1",
        row_number=2,
        source_url=f"https://example.invalid/{doc}",
        post_id=doc,
        author="kutato_fixture",
        author_fullname="Synthetic Fixture",
        caption=caption,
        created_at="2026-04-01T12:00:00",
        collected_at="2026-04-02T12:00:00",
        media_ref=media,
        exact_fingerprint=doc,
        near_duplicate_key=caption.casefold(),
        raw_fields={"caption": caption, "platform_extra": "preserved"},
    )


def test_private_runtime_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="private runtime is incomplete"):
        private_runtime_preflight(tmp_path)


def test_audit_keeps_platforms_and_missingness() -> None:
    records = [record("a", "instagram"), record("b", "tiktok", media="")]
    report = audit_records(records)
    assert report["records"] == 2
    assert report["platform_counts"] == {"instagram": 1, "tiktok": 1}
    assert report["missingness"]["media_ref"] == 1
    assert report["checks"]["original_hungarian_preserved"] is True


def test_pilot_is_deterministic_and_platform_balanced() -> None:
    records = [record(f"ig-{n}", "instagram") for n in range(5)] + [
        record(f"tt-{n}", "tiktok") for n in range(5)
    ]
    first = deterministic_pilot(records, per_platform=2)
    second = deterministic_pilot(reversed(records), per_platform=2)
    assert [r.document_id for r in first] == [r.document_id for r in second]
    assert sum(r.platform == "instagram" for r in first) == 2
    assert sum(r.platform == "tiktok" for r in first) == 2


def test_codebook_collision_queue_detects_ambiguous_alias() -> None:
    book = Codebook(
        codebook_id="hu-private",
        version="1",
        title="fixture",
        project="hungary26",
        entries=[
            CodebookEntry(kind="entity", label="Alpha", aliases=["közös"]),
            CodebookEntry(kind="entity", label="Beta", aliases=["közös"]),
        ],
    )
    collisions = codebook_collisions(book)
    assert collisions == [
        {"surface": "közös", "canonical_labels": ["Alpha", "Beta"], "review_required": True}
    ]


def test_raw_hungarian_and_platform_fields_survive_projection() -> None:
    item = record("x", "instagram", caption="Őrizzük meg az eredeti szöveget")
    payload = item.to_dict()
    assert payload["caption"] == "Őrizzük meg az eredeti szöveget"
    assert payload["raw_fields"]["platform_extra"] == "preserved"
    assert payload["provenance"]["row"] == 2
