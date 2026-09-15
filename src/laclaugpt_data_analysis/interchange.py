"""Serialization and bounded legacy adapters for the canonical record."""
from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .canonical import (
    CanonicalRecord,
    ContentSection,
    FrameReference,
    MediaReference,
    OcrObservation,
    SourceSection,
    Transcript,
)

NESTED_COLUMNS = (
    "source_native_ids",
    "source",
    "content",
    "evidence",
    "analysis",
    "provenance",
    "review",
    "legacy",
)


def record_to_json(record: CanonicalRecord) -> str:
    return json.dumps(record.canonical_dict(), ensure_ascii=False, sort_keys=True)


def record_from_json(payload: str) -> CanonicalRecord:
    return CanonicalRecord.model_validate_json(payload)


def record_to_flat_row(record: CanonicalRecord) -> dict[str, str]:
    raw = record.canonical_dict()
    row: dict[str, str] = {
        "schema_version": record.schema_version,
        "source_url": record.source_url,
    }
    for key in NESTED_COLUMNS:
        row[key] = json.dumps(raw[key], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return row


def record_from_flat_row(row: Mapping[str, Any]) -> CanonicalRecord:
    payload: dict[str, Any] = {
        "schema_version": _scalar(row.get("schema_version")) or "1.0.0",
        "source_url": _scalar(row.get("source_url")),
    }
    for key in NESTED_COLUMNS:
        value = row.get(key)
        payload[key] = _json_cell(value, [] if key in {"evidence", "provenance"} else {})
    return CanonicalRecord.model_validate(payload)


def write_jsonl(path: str | Path, records: Iterable[CanonicalRecord]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record_to_json(record) + "\n")


def read_jsonl(path: str | Path) -> list[CanonicalRecord]:
    source = Path(path)
    if not source.exists():
        return []
    return [record_from_json(line) for line in source.read_text(encoding="utf-8").splitlines() if line]


def write_csv(path: str | Path, records: Iterable[CanonicalRecord]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = [record_to_flat_row(record) for record in records]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["schema_version", "source_url", *NESTED_COLUMNS])
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: str | Path) -> list[CanonicalRecord]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8", newline="") as handle:
        return [record_from_flat_row(row) for row in csv.DictReader(handle)]


def to_mongo_document(record: CanonicalRecord) -> dict[str, Any]:
    """Mongo document form. `_id` is intentionally not source identity."""
    return record.canonical_dict()


def from_mongo_document(document: Mapping[str, Any]) -> CanonicalRecord:
    payload = {key: value for key, value in document.items() if key != "_id"}
    return CanonicalRecord.model_validate(payload)


def from_collection_record(record: Mapping[str, Any]) -> CanonicalRecord:
    """Adapt the current Data Collection NormalizedRecord dictionary."""
    source_url = _scalar(record.get("source_url"))
    document_id = _scalar(record.get("document_id"))
    media = [
        MediaReference(
            kind=_scalar(item.get("kind")),
            url=_scalar(item.get("url")),
            object_ref=_none_if_blank(item.get("object_ref")),
            checksum=_none_if_blank(item.get("checksum")),
            metadata={"media_index": item.get("media_index", 0)},
        )
        for item in (record.get("media_references") or [])
    ]
    collection_prov = dict(record.get("collection_provenance") or {})
    provenance = []
    if collection_prov:
        from .models import Provenance

        provenance.append(
            Provenance(
                method=collection_prov.get("collector", "collection"),
                model=None,
                model_version=collection_prov.get("collector_version") or None,
                metadata={"stage": "collection", **collection_prov},
            )
        )
    return CanonicalRecord(
        schema_version="1.0.0",
        source_url=source_url,
        source_native_ids={"document_id": document_id} if document_id else {},
        source=SourceSection(
            platform=_scalar(record.get("platform")),
            author=_scalar(record.get("author")),
            author_fullname=_scalar(record.get("author_fullname")),
            language=_scalar(record.get("language")),
            parent_source_url=_none_if_blank(record.get("parent_source_url")),
            raw_ref=_none_if_blank(record.get("raw_ref")),
            raw_metadata={"engagement": record.get("engagement") or {}},
        ),
        content=ContentSection(
            text=_scalar(record.get("text")),
            language=_none_if_blank(record.get("language")),
            media_references=media,
        ),
        provenance=provenance,
    )


def from_cyborganthropology(record: Mapping[str, Any]) -> CanonicalRecord:
    """Adapt the public CyborgAnthropology ScrapedItem contract."""
    media: list[MediaReference] = []
    if record.get("local_file") or record.get("allas_file"):
        media.append(
            MediaReference(
                kind="file",
                url="",
                local_ref=_none_if_blank(record.get("local_file")),
                object_ref=_none_if_blank(record.get("allas_file")),
            )
        )
    return CanonicalRecord(
        source_url=_scalar(record.get("scraper_url")),
        source=SourceSection(
            source_type=_scalar(record.get("scraper_type")),
            collection_method=_scalar(record.get("source_type")),
            collector=_scalar(record.get("collector_id")),
            raw_metadata=dict(record.get("scraper_json") or {}),
            raw_ref=_none_if_blank(record.get("scraper_file")),
        ),
        content=ContentSection(text=_scalar(record.get("scraper_text")), media_references=media),
        legacy={"research_note_present": bool(record.get("research_note"))},
    )


def from_ep24_legacy(row: Mapping[str, Any]) -> CanonicalRecord:
    """Map useful EP24-era flat columns into structured optional sections."""
    source_url = _scalar(row.get("source_url") or row.get("video_url"))
    if not source_url:
        author = _scalar(row.get("authorUniqueId") or row.get("author_username"))
        video_id = _scalar(row.get("videoId") or row.get("video_id") or row.get("video_filename"))
        source_url = f"tiktok:{author}:{video_id}" if author else f"legacy:{video_id}"

    transcript_text = _scalar(row.get("whisper_transcript") or row.get("whisperResult"))
    transcript = []
    if transcript_text:
        transcript.append(
            Transcript(
                id="transcript_1",
                text=transcript_text,
                language=_none_if_blank(row.get("whisper_language")),
                translated_text=_none_if_blank(row.get("whisper_translated")),
                provider="whisper",
            )
        )

    ocr: list[OcrObservation] = []
    frames: list[FrameReference] = []
    for index in range(1, 7):
        timestamp = float((index - 1) * 30)
        ocr_text = _scalar(row.get(f"ocr_{index}"))
        frame_analysis = _scalar(row.get(f"frame_analysis_{index}"))
        frame_id = f"frame_{index}"
        if ocr_text or frame_analysis:
            frames.append(
                FrameReference(
                    id=frame_id,
                    timestamp_seconds=timestamp,
                    description=frame_analysis or None,
                )
            )
        if ocr_text:
            ocr.append(
                OcrObservation(
                    id=f"ocr_{index}",
                    text=ocr_text,
                    frame_ref=frame_id,
                    timestamp_seconds=timestamp,
                )
            )

    canonical = CanonicalRecord(
        source_url=source_url,
        source_native_ids={
            key: _scalar(row.get(key))
            for key in ("videoId", "video_id", "video_filename")
            if _scalar(row.get(key))
        },
        source=SourceSection(
            platform="tiktok",
            author=_scalar(row.get("authorUniqueId") or row.get("author_username")),
            language=_scalar(row.get("language")),
        ),
        content=ContentSection(
            text=_scalar(row.get("videoDescription") or row.get("text")),
            transcripts=transcript,
            ocr=ocr,
            frames=frames,
        ),
    )
    summary = _scalar(row.get("summary_analysis"))
    if summary:
        canonical.analysis.summary = summary
        canonical.analysis.status = "analyzed"
    for legacy_name in ("entities", "topics", "positive", "neutral", "negative"):
        value = _scalar(row.get(legacy_name))
        if value:
            canonical.legacy[legacy_name] = value
    return canonical


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def _none_if_blank(value: Any) -> str | None:
    return _scalar(value) or None


def _json_cell(value: Any, default: Any) -> Any:
    text = _scalar(value)
    if not text:
        return default
    return json.loads(text)
