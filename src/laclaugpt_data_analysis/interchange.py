"""Serialization and lossless legacy adapters for the canonical research record."""
from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .canonical import (
    SCHEMA_VERSION,
    CanonicalRecord,
    ContentSection,
    FrameReference,
    HumanReadableSection,
    IntermediateSection,
    MediaReference,
    OcrObservation,
    RawCaptureSection,
    SourceSection,
    Transcript,
)
from .models import Provenance
from .research_record import LEGACY_RESEARCH_COLUMNS, ensure_research_layers, legacy_projection
from .schema_version import normalize_schema_version

NESTED_COLUMNS = (
    "source_native_ids",
    "raw_capture",
    "source",
    "content",
    "intermediate",
    "evidence",
    "analysis",
    "human_readable",
    "provenance",
    "review",
    "legacy",
)


def record_to_json(record: CanonicalRecord) -> str:
    ensure_research_layers(record)
    return json.dumps(record.canonical_dict(), ensure_ascii=False, sort_keys=True)


def record_from_json(payload: str) -> CanonicalRecord:
    return normalize_schema_version(json.loads(payload))


def record_to_flat_row(record: CanonicalRecord) -> dict[str, str]:
    """Return nested canonical JSON plus a stable EP24-style wide projection."""
    ensure_research_layers(record)
    raw = record.canonical_dict()
    row: dict[str, str] = {
        "schema_version": record.schema_version,
        "source_url": record.source_url,
    }
    for key in NESTED_COLUMNS:
        row[key] = json.dumps(raw[key], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    projection = legacy_projection(record)
    for key in LEGACY_RESEARCH_COLUMNS:
        value = projection.get(key, "")
        if isinstance(value, (dict, list, tuple)):
            row[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            row[key] = "" if value is None else str(value)
    return row


def record_from_flat_row(row: Mapping[str, Any]) -> CanonicalRecord:
    # Historical researcher dataframes do not contain nested canonical JSON.
    if not _scalar(row.get("source")) and any(
        _scalar(row.get(key))
        for key in ("whisper_transcript", "summary_analysis", "frame_1", "ocr_1", "new_id")
    ):
        return from_ep24_legacy(row)

    payload: dict[str, Any] = {
        "schema_version": _scalar(row.get("schema_version")) or SCHEMA_VERSION,
        "source_url": _scalar(row.get("source_url")),
    }
    for key in NESTED_COLUMNS:
        value = row.get(key)
        payload[key] = _json_cell(value, [] if key in {"evidence", "provenance"} else {})
    record = normalize_schema_version(payload)
    # Preserve any wide aliases supplied by a researcher/export in addition to nested JSON.
    for key in LEGACY_RESEARCH_COLUMNS:
        if key in row and _scalar(row.get(key)):
            record.legacy.setdefault(key, row.get(key))
    return ensure_research_layers(record)


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
    """Write the canonical record and old-dashboard-compatible columns side by side."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = [record_to_flat_row(record) for record in records]
    fields = ["schema_version", "source_url", *NESTED_COLUMNS, *LEGACY_RESEARCH_COLUMNS]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: str | Path) -> list[CanonicalRecord]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8", newline="") as handle:
        return [record_from_flat_row(row) for row in csv.DictReader(handle)]


def write_sqlite(path: str | Path, records: Iterable[CanonicalRecord]) -> None:
    """Persist complete canonical JSON keyed by source_url, never backend identity."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in records:
        ensure_research_layers(record)
        rows.append((record.source_url, record.schema_version, record_to_json(record)))
    with sqlite3.connect(destination) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS canonical_records (
                source_url TEXT PRIMARY KEY,
                schema_version TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )"""
        )
        connection.executemany(
            """INSERT INTO canonical_records(source_url, schema_version, payload_json)
               VALUES (?, ?, ?)
               ON CONFLICT(source_url) DO UPDATE SET
                 schema_version=excluded.schema_version,
                 payload_json=excluded.payload_json""",
            rows,
        )
        connection.commit()


def read_sqlite(path: str | Path) -> list[CanonicalRecord]:
    source = Path(path)
    if not source.exists():
        return []
    with sqlite3.connect(source) as connection:
        try:
            rows = connection.execute(
                "SELECT payload_json FROM canonical_records ORDER BY source_url"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [record_from_json(payload) for (payload,) in rows]


def to_mongo_document(record: CanonicalRecord) -> dict[str, Any]:
    """Mongo document contains all four layers. `_id` is never source identity."""
    ensure_research_layers(record)
    return record.canonical_dict()


def from_mongo_document(document: Mapping[str, Any]) -> CanonicalRecord:
    payload = {key: value for key, value in document.items() if key != "_id"}
    return ensure_research_layers(normalize_schema_version(payload))


def _collection_provenance(values: Any) -> list[Provenance]:
    result: list[Provenance] = []
    for item in values or []:
        if not isinstance(item, Mapping):
            continue
        if item.get("method"):
            result.append(Provenance.model_validate(item))
            continue
        result.append(
            Provenance(
                provenance_id=_scalar(item.get("provenance_id")) or Provenance(method="collection").provenance_id,
                method=_scalar(item.get("collector") or item.get("module")) or "collection",
                model_version=_none_if_blank(item.get("collector_version") or item.get("module_version")),
                created_at=item.get("captured_at"),
                metadata={"stage": "collection", **dict(item)},
            )
        )
    return result


def from_collection_record(record: Mapping[str, Any]) -> CanonicalRecord:
    """Adapt Collection 1.0/1.1 dictionaries without dropping raw or researcher layers."""
    if isinstance(record.get("source"), Mapping):
        source_data = dict(record.get("source") or {})
        content_data = dict(record.get("content") or {})
        media = [MediaReference.model_validate(item) for item in content_data.get("media_references", [])]
        content_data["media_references"] = media
        canonical = CanonicalRecord(
            schema_version=SCHEMA_VERSION,
            source_url=_scalar(record.get("source_url")),
            source_native_ids={str(k): str(v) for k, v in dict(record.get("source_native_ids") or {}).items()},
            raw_capture=RawCaptureSection.model_validate(
                record.get("raw_capture")
                or {
                    "ref": source_data.get("raw_ref"),
                    "payload": None,
                    "metadata": {"preservation": "collection-legacy-reference-only"},
                }
            ),
            source=SourceSection.model_validate(source_data),
            content=ContentSection.model_validate(content_data),
            intermediate=IntermediateSection.model_validate(record.get("intermediate") or {}),
            evidence=list(record.get("evidence") or []),
            analysis=dict(record.get("analysis") or {}),
            human_readable=HumanReadableSection.model_validate(record.get("human_readable") or {}),
            provenance=_collection_provenance(record.get("provenance")),
            review=dict(record.get("review") or {}),
            legacy=dict(record.get("legacy") or {}),
        )
        return ensure_research_layers(canonical)

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
    raw_ref = _none_if_blank(record.get("raw_ref"))
    collection_prov = dict(record.get("collection_provenance") or {})
    provenance = _collection_provenance([collection_prov] if collection_prov else [])
    canonical = CanonicalRecord(
        source_url=source_url,
        source_native_ids={"document_id": document_id} if document_id else {},
        raw_capture=RawCaptureSection(
            ref=raw_ref,
            payload=record.get("raw_payload"),
            metadata={"preservation": "legacy-collection-adapter"},
        ),
        source=SourceSection(
            platform=_scalar(record.get("platform")),
            author=_scalar(record.get("author")),
            author_fullname=_scalar(record.get("author_fullname")),
            language=_scalar(record.get("language")),
            parent_source_url=_none_if_blank(record.get("parent_source_url")),
            raw_ref=raw_ref,
            raw_metadata={"engagement": record.get("engagement") or {}},
        ),
        content=ContentSection(
            text=_scalar(record.get("text")),
            language=_none_if_blank(record.get("language")),
            media_references=media,
        ),
        provenance=provenance,
    )
    return ensure_research_layers(canonical)


def from_cyborganthropology(record: Mapping[str, Any]) -> CanonicalRecord:
    """Adapt the public CyborgAnthropology ScrapedItem contract losslessly."""
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
    raw_payload = record.get("scraper_json")
    raw_ref = _none_if_blank(record.get("scraper_file"))
    canonical = CanonicalRecord(
        source_url=_scalar(record.get("scraper_url")),
        raw_capture=RawCaptureSection(
            ref=raw_ref,
            payload=raw_payload,
            content_type="application/json" if raw_payload is not None else None,
            metadata={"preservation": "legacy-cyborganthropology"},
        ),
        source=SourceSection(
            source_type=_scalar(record.get("scraper_type")),
            collection_method=_scalar(record.get("source_type")),
            collector=_scalar(record.get("collector_id")),
            raw_metadata=dict(raw_payload or {}),
            raw_ref=raw_ref,
        ),
        content=ContentSection(text=_scalar(record.get("scraper_text")), media_references=media),
        legacy={"research_note_present": bool(record.get("research_note"))},
    )
    return ensure_research_layers(canonical)


def from_ep24_legacy(row: Mapping[str, Any]) -> CanonicalRecord:
    """Losslessly import an EP24-era researcher dataframe row into the new record."""
    source_url = _scalar(row.get("source_url") or row.get("video_url"))
    if not source_url:
        author = _scalar(row.get("authorUniqueId") or row.get("author_username"))
        video_id = _scalar(row.get("videoId") or row.get("video_id") or row.get("video_filename") or row.get("new_id"))
        source_url = f"tiktok:{author}:{video_id}" if author else f"legacy:{video_id}"

    transcript_text = _scalar(row.get("whisper_transcript") or row.get("whisperResult"))
    transcript: list[Transcript] = []
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
        frame_analysis = _scalar(row.get(f"frame_analysis_{index}") or row.get(f"frame_{index}"))
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

    native_ids = {
        key: _scalar(row.get(key))
        for key in ("videoId", "video_id", "video_filename", "new_id", "old_id")
        if _scalar(row.get(key))
    }
    legacy = {str(key): value for key, value in row.items() if _scalar(value)}
    canonical = CanonicalRecord(
        source_url=source_url,
        source_native_ids=native_ids,
        raw_capture=RawCaptureSection(
            payload=dict(row),
            content_type="text/csv-row",
            metadata={
                "preservation": "legacy-dataframe-row",
                "warning": "This is the historical dataframe row, not the original platform API payload.",
            },
        ),
        source=SourceSection(
            platform=_scalar(row.get("source_type")) or "tiktok",
            source_type=_scalar(row.get("source_type")),
            author=_scalar(row.get("authorUniqueId") or row.get("author_username")),
            language=_scalar(row.get("language") or row.get("whisper_language")),
            country=_scalar(row.get("country")),
            raw_metadata={
                "account_type": row.get("account_type"),
                "political_preference": row.get("political_preference"),
                "profile_name": row.get("profile_name"),
            },
        ),
        content=ContentSection(
            text=_scalar(row.get("videoDescription") or row.get("text")),
            transcripts=transcript,
            ocr=ocr,
            frames=frames,
        ),
        legacy=legacy,
    )
    summary = _scalar(row.get("summary_analysis"))
    if summary:
        canonical.analysis.summary = summary
        canonical.analysis.status = "analyzed"
    return ensure_research_layers(canonical)


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
