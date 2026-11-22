"""#504: a timestamp that a datetime range query can actually find.

The analysis collections were written with ``created_at = time.time()`` while every reader asks a datetime
range question. MongoDB compares types, not values, so ``{"created_at": {"$gte": datetime(...)}}`` matched
nothing in a float field — 0 results and 0 failures over data that plainly existed, which is exactly what a
stalled pipeline looks like from the outside.

Two contracts are pinned here:

1. new documents store a timezone-aware datetime (:func:`now_utc`);
2. readers that must also see pre-#504 float documents use :func:`time_window_filter`, which matches either
   representation instead of demanding a backfill before the first useful answer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from laclaugpt_data_analysis.timequery import now_utc, time_window_filter

SINCE = datetime(2026, 11, 21, tzinfo=UTC)
UNTIL = SINCE + timedelta(days=1)


def test_new_documents_carry_a_timezone_aware_datetime():
    value = now_utc()
    assert isinstance(value, datetime), "a float epoch would match no datetime range query"
    assert value.tzinfo is not None


def test_the_filter_matches_both_representations_by_default():
    window = time_window_filter("created_at", SINCE, UNTIL)
    alternatives = window["$or"]
    assert len(alternatives) == 2

    modern = next(a for a in alternatives if isinstance(a["created_at"]["$gte"], datetime))
    legacy = next(a for a in alternatives if isinstance(a["created_at"]["$gte"], float))
    assert modern["created_at"]["$gte"] == SINCE
    assert legacy["created_at"]["$gte"] == pytest.approx(SINCE.timestamp())


def test_legacy_matching_can_be_dropped_after_a_backfill():
    window = time_window_filter("created_at", SINCE, UNTIL, include_legacy_epoch=False)
    assert "$or" not in window
    assert isinstance(window["created_at"]["$gte"], datetime)


def test_naive_bounds_are_refused():
    with pytest.raises(ValueError):
        time_window_filter("created_at", datetime(2026, 11, 21))


def test_an_open_ended_window_has_no_upper_bound():
    window = time_window_filter("created_at", SINCE)
    modern = window["$or"][0]["created_at"]
    assert "$gte" in modern and "$lt" not in modern
