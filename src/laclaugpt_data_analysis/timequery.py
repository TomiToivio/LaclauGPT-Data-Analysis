"""Time-range filters for collections written by more than one producer (#504).

The AI26 analysis collections were written with ``created_at = time.time()`` (a float epoch), while every
natural reader — and every monitor — asks a ``datetime`` range question. MongoDB compares types, not values:
``{"created_at": {"$gte": datetime(...)}}`` matches **nothing** in a float field, and returns an empty result
that looks exactly like a quiet hour.

Two things fix that, and both are needed:

- new documents carry a real BSON ``datetime`` (:func:`now_utc`, used by the Mongo store);
- readers that must also see documents written before the change use :func:`time_window_filter`, which
  matches either representation rather than requiring a backfill before the first useful answer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def now_utc() -> datetime:
    """The value a new document should store: a timezone-aware datetime, not an epoch float."""
    return datetime.now(UTC)


def time_window_filter(
    field: str,
    since: datetime,
    until: datetime | None = None,
    *,
    include_legacy_epoch: bool = True,
) -> dict[str, Any]:
    """MongoDB filter matching ``field`` inside ``[since, until)`` in either representation.

    ``include_legacy_epoch`` exists because documents written before #504 hold a float epoch. Set it to
    ``False`` once a backfill has run, and the filter becomes the plain datetime comparison.
    """
    if since.tzinfo is None or (until is not None and until.tzinfo is None):
        raise ValueError("time_window_filter needs timezone-aware bounds")

    def _bounds(low: Any, high: Any | None) -> dict[str, Any]:
        window: dict[str, Any] = {"$gte": low}
        if high is not None:
            window["$lt"] = high
        return window

    modern = {field: _bounds(since, until)}
    if not include_legacy_epoch:
        return modern
    legacy = {field: _bounds(since.timestamp(), until.timestamp() if until else None)}
    return {"$or": [modern, legacy]}
