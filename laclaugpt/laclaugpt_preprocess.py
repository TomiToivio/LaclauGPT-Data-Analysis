"""Minimal Phase 0 text-only preprocessing helpers.

No OCR, Whisper, OpenCV, Redis, Allas, spaCy, Telegram or multimodal imports.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

TEXT_FIELDS = ("source_text", "article_text", "content", "text", "description", "summary")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def choose_text(record: dict[str, Any]) -> str:
    for field in TEXT_FIELDS:
        text = normalize_text(record.get(field))
        if text:
            return text
    return ""


def stable_document_id(record: dict[str, Any], text: str) -> str:
    source_url = normalize_text(record.get("source_url"))
    basis = source_url or "|".join(
        [
            normalize_text(record.get("source_name")),
            normalize_text(record.get("title")),
            normalize_text(record.get("source_date")),
            text,
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def preprocess_record(record: dict[str, Any]) -> dict[str, Any]:
    text = choose_text(record)
    if not text:
        raise ValueError("No usable text field found")

    document_id = normalize_text(record.get("document_id")) or stable_document_id(record, text)
    now = datetime.now(timezone.utc).isoformat()

    metadata_fields = (
        "source_url",
        "source_date",
        "source_name",
        "source_type",
        "actor_name",
        "arena",
        "ai_formation",
        "political_formation",
        "title",
        "language",
    )
    preserved = {key: record.get(key) for key in metadata_fields if record.get(key) is not None}

    return {
        "document_id": document_id,
        "normalized_text": text,
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "metadata": preserved,
        "phase0": {
            **dict(record.get("phase0") or {}),
            "preprocess": {"status": "ok", "updated_at": now},
        },
    }
