"""#504: a datetime query against a float `created_at` returns zero, silently.

Both analysis collections stored `created_at` as `time.time()`. MongoDB does not complain
about comparing a BSON date to a double — it matches nothing. So "what happened in the last
24 hours" answered 0 while 5,393 results and 1,675 failures sat in the database, and a
pipeline that had stopped looked like a quiet hour.

These tests pin the write type and the read helper, and — importantly — simulate the match
so "the filter finds the legacy rows" is proven rather than described.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from laclaugpt_data_analysis.timestamps import created_at_of, since_filter, utc_now

ROOT = Path(__file__).resolve().parents[1]


def matches(document: dict, query: dict) -> bool:
    """Minimal `$or` / `$gte` evaluator: enough to prove the filter's intent."""
    for clause in query["$or"]:
        field, condition = next(iter(clause.items()))
        value, bound = document.get(field), condition["$gte"]
        if value is None:
            continue
        if isinstance(value, datetime) and isinstance(bound, datetime) and value >= bound:
            return True
        if isinstance(value, (int, float)) and not isinstance(value, bool) and isinstance(bound, (int, float)):
            if value >= bound:
                return True
        if isinstance(value, datetime) and isinstance(bound, (int, float)) and value.timestamp() >= bound:
            return True
    return False


def test_the_write_clock_is_timezone_aware():
    now = utc_now()
    assert isinstance(now, datetime) and now.tzinfo is not None


def test_the_filter_matches_a_legacy_float_row():
    """The whole bug: this row was invisible to a datetime query."""
    cutoff = utc_now() - timedelta(days=1)
    legacy = {"created_at": (utc_now() - timedelta(hours=2)).timestamp()}
    assert matches(legacy, since_filter(cutoff)) is True


def test_the_filter_matches_a_datetime_row():
    cutoff = utc_now() - timedelta(days=1)
    modern = {"created_at": utc_now() - timedelta(hours=2)}
    assert matches(modern, since_filter(cutoff)) is True


def test_the_filter_excludes_old_rows_of_both_types():
    cutoff = utc_now()
    old = utc_now() - timedelta(days=3)
    assert matches({"created_at": old}, since_filter(cutoff)) is False
    assert matches({"created_at": old.timestamp()}, since_filter(cutoff)) is False


def test_a_naive_cutoff_is_read_as_utc_rather_than_rejected():
    naive = datetime(2026, 11, 21, 12, 0)
    assert since_filter(naive)["$or"][0]["created_at"]["$gte"].tzinfo is UTC


def test_reading_a_document_handles_both_representations():
    moment = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
    assert created_at_of({"created_at": moment}) == moment
    assert created_at_of({"created_at": moment.timestamp()}) == moment
    assert created_at_of({"created_at_epoch": moment.timestamp()}) == moment
    assert created_at_of({}) is None and created_at_of(None) is None


def test_both_analysis_writers_store_a_datetime():
    source = (ROOT / "src" / "laclaugpt_data_analysis" / "task_queue.py").read_text(encoding="utf-8")
    assert source.count('"created_at": utc_now()') == 2, "results and failures must both use it"
    assert '"created_at": time.time()' not in source, "the float write is the defect"
    assert source.count('"created_at_epoch": time.time()') == 2, "the epoch stays available beside it"
