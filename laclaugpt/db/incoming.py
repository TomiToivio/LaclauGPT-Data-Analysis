"""Read records that are ready for a given step.

A step should never decide for itself which records are eligible: that rule lives
here, in one place, so the run order is auditable.

Eligibility for a step is deliberately simple and explicit:

1. the step has not already produced a successful result for the record, unless a
   retry is requested;
2. no earlier step left the record in a failed state (otherwise a record stuck at
   step 1 would be processed by steps 3, 5, 7 forever);
3. for media steps, the record actually carries media.

A text-only record is a valid record. Step 2 must skip it cleanly rather than
treat it as a failure.
"""
from __future__ import annotations

from typing import Any, Iterable

from models.incoming import IncomingRecord, MediaItem, SourceInfo

# Steps that require media. Mirrors the ``needs_media`` flags in steps/__init__.py.
MEDIA_STEPS = frozenset({"preprocess", "frame_analysis"})


def incoming_from_document(document: dict[str, Any]) -> IncomingRecord:
    """Build the readable record from a stored document.

    This is the one place that knows how a persisted document maps onto
    ``IncomingRecord``. Collection output is passed through in ``raw_metadata``
    rather than reinterpreted here.
    """
    raw_source = document.get("source")
    source: dict[str, Any] = raw_source if isinstance(raw_source, dict) else {}
    media = [
        MediaItem(
            kind=str(item.get("kind") or item.get("media_type") or ""),
            url=str(item.get("url") or item.get("ref") or ""),
            local_path=item.get("local_path") or item.get("local_ref"),
            checksum=item.get("checksum"),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in (document.get("media") or document.get("media_references") or [])
        if isinstance(item, dict)
    ]
    return IncomingRecord(
        source_url=str(document.get("source_url", "")),
        source=SourceInfo(
            platform=str(source.get("platform") or document.get("platform") or ""),
            source_name=str(source.get("source_name") or document.get("source_name") or ""),
            url=str(source.get("url") or document.get("source_url") or ""),
            author=str(source.get("author") or document.get("author") or ""),
            language=source.get("language") or document.get("source_language"),
            country=source.get("country") or document.get("source_country"),
            arena=source.get("arena") or document.get("arena"),
            metadata=dict(source.get("metadata") or {}),
        ),
        text=str(document.get("source_text") or document.get("text") or ""),
        title=document.get("title"),
        language=document.get("source_language") or source.get("language"),
        media=media,
        raw_metadata=dict(document.get("raw_metadata") or {}),
        step_outputs=dict(document.get("step_outputs") or {}),
    )


def step_status(document: dict[str, Any], step: str) -> str | None:
    """The recorded status of ``step`` on this document, if any."""
    block = (document.get("step_outputs") or {}).get(step)
    if isinstance(block, dict):
        return block.get("status")
    return None


def earlier_failed(document: dict[str, Any], step: str, order_of: dict[str, int]) -> bool:
    """Whether any step before ``step`` recorded a failure."""
    target = order_of.get(step)
    if target is None:
        return False
    for other, order in order_of.items():
        if order < target and step_status(document, other) == "failed":
            return True
    return False


def is_eligible(
    document: dict[str, Any],
    step: str,
    *,
    order_of: dict[str, int],
    retry_errors: bool = False,
) -> bool:
    """Whether this document should be processed by ``step`` now."""
    status = step_status(document, step)
    if status == "ran" and not retry_errors:
        return False
    if status == "failed":
        # A failed step is retried only when explicitly asked for.
        if not retry_errors:
            return False
    elif earlier_failed(document, step, order_of):
        return False

    if step in MEDIA_STEPS and not document.get("media") and not document.get("media_references"):
        # Nothing for a media step to read. Not an error; simply not applicable.
        return False
    return True


def ready_documents(
    documents: Iterable[dict[str, Any]],
    step: str,
    *,
    order_of: dict[str, int],
    retry_errors: bool = False,
) -> list[dict[str, Any]]:
    """Filter a batch down to the documents this step should handle."""
    return [
        document
        for document in documents
        if is_eligible(document, step, order_of=order_of, retry_errors=retry_errors)
    ]
