"""Timestamp handling for the ``ai26__*`` analysis collections (#504).

The analysis result and failure writers stored ``created_at`` as ``time.time()`` — a float.
A BSON ``datetime`` range query against a float field is not an error in MongoDB: it simply
matches nothing. So the natural "what happened in the last 24 hours" query returned zero
documents while both collections held thousands, and a stalled pipeline looked exactly like
a quiet hour. That is the one failure a monitor exists to rule out.

Two rules follow, and they are the whole point of this module:

1. **Write** ``created_at`` as a timezone-aware ``datetime``. The epoch is written beside it
   as ``created_at_epoch`` for anything that wants a number, so no consumer has to guess.
2. **Read** through :func:`since_filter`, which matches both representations, because the
   documents written before this change are still float and are not being rewritten.

A migration is deliberately not attempted: the float values are epoch seconds, but rewriting
thousands of documents to prove a point risks more than a query helper costs. The helper
makes old rows readable; the writer makes new rows answerable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

#: Fields that may carry the creation timestamp, newest name first.
_CREATED_AT_FIELDS = ("created_at", "created_at_epoch")


def utc_now() -> datetime:
    """The write-side clock: timezone-aware, so MongoDB stores a real BSON date."""
    return datetime.now(UTC)


def since_filter(since: datetime) -> dict[str, Any]:
    """A ``$gte`` filter that matches datetime *and* legacy float ``created_at`` values.

    Use this instead of ``{"created_at": {"$gte": since}}`` anywhere a caller wants "since
    this moment": the direct filter silently returns nothing against the rows written before
    #504, which is the defect being fixed rather than a thing to work around at each call site.
    """
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    return {
        "$or": [
            {"created_at": {"$gte": since}},
            {"created_at": {"$gte": since.timestamp()}},
        ]
    }


def created_at_of(document: Mapping[str, Any] | None) -> datetime | None:
    """Read a document's creation time as a datetime, whichever representation it stored."""
    if not document:
        return None
    for field in _CREATED_AT_FIELDS:
        value = document.get(field)
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(float(value), tz=UTC)
    return None
