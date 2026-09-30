"""Native compatibility with the real DATS CSV interchange surface.

DATS (Discourse Analysis Tool Suite) exports/imports researcher-facing CSV tables,
often packaged in ZIP files. This module maps the parts LaclauGPT can represent
without pretending DATS carries SNA or Laclaudian semantics.

Verified against uhh-lt/dats v1.11.1 export schemas:
- source documents
- hierarchical codes
- span annotations
- memos

Unsupported DATS-only objects remain outside the canonical model rather than being
fabricated as network relations.
"""
from __future__ import annotations

import ast
import csv
import io
import json
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .contracts import DatsProject


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))


def _literal(value: str | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return default


def import_dats_csv_tables(tables: Mapping[str, str]) -> dict[str, Any]:
    """Map real DATS CSV tables to the normalized project payload used internally."""
    payload: dict[str, Any] = {
        "project_id": "dats-project",
        "documents": [],
        "codes": [],
        "annotations": [],
        "memos": [],
        "metadata": {"source_format": "dats-csv"},
    }

    for name, text in tables.items():
        rows = _rows(text)
        if not rows:
            continue
        fields = set(rows[0])

        if {"filename", "name", "doctype", "status", "content"} <= fields:
            for row in rows:
                metadata_pairs = _literal(row.get("metadata"), [])
                metadata = dict(metadata_pairs) if isinstance(metadata_pairs, list) else {}
                payload["documents"].append(
                    {
                        "id": row["filename"],
                        "title": row.get("name") or row["filename"],
                        "text": row.get("content") or "",
                        "source_type": row.get("doctype") or "text",
                        "metadata": {
                            **metadata,
                            "dats_status": row.get("status"),
                            "dats_tags": _literal(row.get("tags"), []),
                            "dats_filename": row["filename"],
                        },
                    }
                )
            continue

        if {"code_name", "description", "parent_code_name"} <= fields:
            for row in rows:
                payload["codes"].append(
                    {
                        "id": row["code_name"],
                        "label": row["code_name"],
                        "parent_id": row.get("parent_code_name") or None,
                        "description": row.get("description") or None,
                    }
                )
            continue

        if {
            "uuid",
            "sdoc_name",
            "user_email",
            "code_name",
            "text_begin_char",
            "text_end_char",
        } <= fields:
            for row in rows:
                payload["annotations"].append(
                    {
                        "id": row["uuid"],
                        "document_id": row["sdoc_name"],
                        "code_id": row["code_name"],
                        "start": int(row["text_begin_char"]),
                        "end": int(row["text_end_char"]),
                        "producer_type": "human",
                        "producer_id": row["user_email"],
                        "metadata": {
                            "dats_text": row.get("text") or "",
                            "text_begin_token": row.get("text_begin_token"),
                            "text_end_token": row.get("text_end_token"),
                        },
                    }
                )
            continue

        if {"uuid", "user_email", "title", "attached_type", "attached_to"} <= fields:
            for row in rows:
                payload["memos"].append(
                    {
                        "id": row["uuid"],
                        "text": row.get("content") or row.get("title") or "",
                        "producer_type": "human",
                        "producer_id": row["user_email"],
                        "metadata": {
                            "title": row.get("title"),
                            "attached_type": row.get("attached_type"),
                            "attached_to": row.get("attached_to"),
                            "content_json": row.get("content_json"),
                        },
                    }
                )
            continue

        payload["metadata"].setdefault("unmapped_tables", []).append(name)

    return payload


def load_dats_export(path: str | Path) -> dict[str, Any]:
    """Load a DATS CSV or ZIP-of-CSV export into the normalized payload."""
    source = Path(path)
    tables: dict[str, str] = {}
    if source.suffix.casefold() == ".zip":
        def collect_zip(archive: zipfile.ZipFile, prefix: str = "") -> None:
            for member in archive.namelist():
                name = f"{prefix}{member}"
                lowered = member.casefold()
                if lowered.endswith(".csv"):
                    tables[name] = archive.read(member).decode("utf-8-sig")
                elif lowered.endswith(".zip"):
                    nested = io.BytesIO(archive.read(member))
                    with zipfile.ZipFile(nested) as child:
                        collect_zip(child, prefix=f"{name}!/")
        with zipfile.ZipFile(source) as archive:
            collect_zip(archive)
    else:
        tables[source.name] = source.read_text(encoding="utf-8-sig")
    return import_dats_csv_tables(tables)


def _csv(fieldnames: list[str], rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fieldnames})
    return buffer.getvalue()


def export_dats_csv_tables(project: DatsProject) -> dict[str, str]:
    """Export real DATS-compatible CSV tables for the mappable research objects.

    The output is designed for DATS's individual CSV import surfaces. Provenance,
    confidence, review state, entities and network semantics remain in LaclauGPT
    because DATS's CSV schemas do not have fields for them.
    """
    documents = []
    document_name: dict[str, str] = {}
    for index, record in enumerate(project.documents, start=1):
        filename = record.source_native_ids.get("dats_document_id") or f"document_{index}.txt"
        document_name[record.source_url] = filename
        documents.append(
            {
                "filename": filename,
                "name": record.content.title or filename,
                "doctype": "text",
                "status": 1,
                "folder_name": "LaclauGPT",
                "folder_parent_name": "",
                "tags": repr([]),
                "word_frequencies": repr([]),
                "metadata": repr(list(record.source.raw_metadata.items())),
                "content": record.content.text,
                "html": "",
                "raw_html": "",
                "token_starts": repr([]),
                "token_ends": repr([]),
                "sentence_starts": repr([]),
                "sentence_ends": repr([]),
                "token_time_starts": "",
                "token_time_ends": "",
                "document_embedding": "",
                "image_embedding": "",
                "sentence_embeddings": repr([]),
            }
        )

    external_code: dict[str, str] = {}
    codes = []
    for code in project.codes:
        dats_id = next((ref.id for ref in code.external_ids if ref.system == "dats"), code.code_id)
        external_code[code.code_id] = dats_id
    for code in project.codes:
        codes.append(
            {
                "code_name": external_code[code.code_id],
                "description": code.description or "",
                "color": "",
                "parent_code_name": external_code.get(code.parent_id or "", code.parent_id or ""),
            }
        )

    evidence = {ev.evidence_id: ev for record in project.documents for ev in record.evidence}
    annotations = []
    for annotation in project.annotations:
        ev = evidence.get(annotation.evidence_id)
        if ev is None or ev.start_offset is None or ev.end_offset is None:
            continue
        dats_id = next(
            (ref.id for ref in annotation.external_ids if ref.system == "dats"),
            annotation.annotation_id,
        )
        annotations.append(
            {
                "uuid": dats_id,
                "sdoc_name": document_name[annotation.source_url],
                "user_email": annotation.producer.id,
                "code_name": external_code.get(annotation.code_id, annotation.code_id),
                "text": ev.quote or "",
                "text_begin_char": ev.start_offset,
                "text_end_char": ev.end_offset,
                "text_begin_token": 0,
                "text_end_token": 0,
                "user_first_name": "",
                "user_last_name": "",
            }
        )

    memos = []
    for note in project.notes:
        dats_id = next((ref.id for ref in note.external_ids if ref.system == "dats"), note.note_id)
        memos.append(
            {
                "uuid": dats_id,
                "user_email": note.producer.id,
                "favorited_by": "[]",
                "title": note.note_id,
                "icon": "",
                "content": note.text,
                "content_json": json.dumps({"text": note.text}, ensure_ascii=False),
                "attached_type": "project",
                "attached_to": "project",
            }
        )

    return {
        "document_export_data.csv": _csv(
            [
                "filename", "name", "doctype", "status", "folder_name",
                "folder_parent_name", "tags", "word_frequencies", "metadata",
                "content", "html", "raw_html", "token_starts", "token_ends",
                "sentence_starts", "sentence_ends", "token_time_starts",
                "token_time_ends", "document_embedding", "image_embedding",
                "sentence_embeddings",
            ],
            documents,
        ),
        "all_codes.csv": _csv(
            ["code_name", "description", "color", "parent_code_name"], codes
        ),
        "all_span_annotations.csv": _csv(
            [
                "uuid", "sdoc_name", "user_email", "code_name", "text",
                "text_begin_char", "text_end_char", "text_begin_token",
                "text_end_token", "user_first_name", "user_last_name",
            ],
            annotations,
        ),
        "all_memos.csv": _csv(
            [
                "uuid", "user_email", "favorited_by", "title", "icon", "content",
                "content_json", "attached_type", "attached_to",
            ],
            memos,
        ),
    }
