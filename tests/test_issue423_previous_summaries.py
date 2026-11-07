"""The previous-window lookup read the whole summary history and stopped fitting (#423).

``generate_latest_reports`` needs exactly one thing from history: for every scope, the
most recent summary *before* the window now being reported. It used to obtain that by
reading every summary the run had ever written — 136,218 documents and 1.3 GB on Laskin
on 2026-11-06, a read projected at ~5,100 s against a 900 s report ceiling. Since
2026-11-05 17:45 no AI26 report has completed at all.

These tests pin the replacement: the history is scanned through a projection of two
small fields, only the retained candidates are read with their payload, and the window
comparison stays a parsed-datetime comparison so stored string formats cannot reorder
which window counts as previous.
"""
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laclaugpt_data_analysis import phase1_laskin_report as report  # noqa: E402

SRC = ROOT / "src" / "laclaugpt_data_analysis"


class _Cursor(list):
    pass


class _Collection:
    """Minimal stand-in for a pymongo collection: equality and ``$in`` filters only."""

    def __init__(self, documents):
        self.documents = documents
        self.calls = []

    def find(self, query, projection=None):
        projection = dict(projection or {})
        self.calls.append((dict(query), projection))

        def matches(document):
            for key, expected in query.items():
                if isinstance(expected, dict) and "$in" in expected:
                    if document.get(key) not in expected["$in"]:
                        return False
                elif document.get(key) != expected:
                    return False
            return True

        selected = [document for document in self.documents if matches(document)]
        return _Cursor(
            {key: document[key] for key in projection if key in document}
            for document in selected
        )


def _summary(scope_key: str, window_end: datetime, *, run_id: str = "ai26-distributed-001"):
    return {
        "project_id": "ai26",
        "run_id": run_id,
        "scope_key": scope_key,
        "window_end": window_end.isoformat(),
        "payload": {"scope": {"key": scope_key}, "window_end": window_end.isoformat()},
    }


def _history(scopes: int, windows: int, *, start: datetime, step_hours: int = 1):
    return [
        _summary(
            f"scope-{scope:02d}",
            start + timedelta(hours=step_hours * window),
        )
        for scope in range(scopes)
        for window in range(windows)
    ]


def test_payload_is_read_only_for_the_newest_candidates_per_scope():
    start = datetime(2026, 11, 1, 0, tzinfo=UTC)
    documents = _history(scopes=20, windows=50, start=start)
    before = start + timedelta(hours=50)  # nothing exists at or after this point
    collection = _Collection(documents)

    loaded = report.load_previous_summary_documents(
        collection, project_id="ai26", run_id="ai26-distributed-001", before=before
    )

    with_payload = [document for document in loaded if "payload" in document]
    assert len(with_payload) <= 20 * report.PREVIOUS_SUMMARIES_PER_SCOPE
    newest = {
        (document["payload"]["scope"]["key"], document["payload"]["window_end"])
        for document in with_payload
        if document["payload"]["window_end"] == (before - timedelta(hours=1)).isoformat()
    }
    assert len(newest) == 20  # every scope still gets its immediately preceding window


def test_the_history_is_scanned_through_two_small_fields_first():
    start = datetime(2026, 11, 1, 0, tzinfo=UTC)
    collection = _Collection(_history(scopes=3, windows=4, start=start))

    report.load_previous_summary_documents(
        collection,
        project_id="ai26",
        run_id="ai26-distributed-001",
        before=start + timedelta(hours=10),
    )

    first_query, first_projection = collection.calls[0]
    assert first_query == {"project_id": "ai26", "run_id": "ai26-distributed-001"}
    assert set(first_projection) == {"scope_key", "window_end", "_id"}
    assert "payload" not in first_projection
    assert "payload" in collection.calls[1][1]


def test_a_window_strictly_after_the_boundary_is_never_a_candidate():
    start = datetime(2026, 11, 1, 0, tzinfo=UTC)
    documents = [
        _summary("scope-a", start),
        _summary("scope-a", start + timedelta(hours=12)),
        _summary("scope-b", start + timedelta(hours=12)),
    ]
    collection = _Collection(documents)

    loaded = report.load_previous_summary_documents(
        collection,
        project_id="ai26",
        run_id="ai26-distributed-001",
        before=start + timedelta(hours=6),
    )

    assert [document["payload"]["window_end"] for document in loaded] == [start.isoformat()]


def test_a_window_ending_exactly_at_the_boundary_is_still_the_previous_window():
    """Adjacent windows meet at the boundary, so ``window_end == before`` must be kept."""
    start = datetime(2026, 11, 1, 0, tzinfo=UTC)
    collection = _Collection([_summary("scope-a", start)])

    loaded = report.load_previous_summary_documents(
        collection,
        project_id="ai26",
        run_id="ai26-distributed-001",
        before=start,
    )

    assert [document["payload"]["window_end"] for document in loaded] == [start.isoformat()]


def test_an_unparseable_window_end_is_ignored_rather_than_compared_as_text():
    start = datetime(2026, 11, 1, 0, tzinfo=UTC)
    documents = [
        _summary("scope-a", start),
        {
            "project_id": "ai26",
            "run_id": "ai26-distributed-001",
            "scope_key": "scope-a",
            "window_end": "not-a-date",
        },
    ]
    collection = _Collection(documents)

    loaded = report.load_previous_summary_documents(
        collection,
        project_id="ai26",
        run_id="ai26-distributed-001",
        before=start + timedelta(hours=1),
    )

    assert [document["payload"]["window_end"] for document in loaded] == [start.isoformat()]


def test_the_report_uses_the_bounded_lookup():
    source = (SRC / "phase1_laskin_report.py").read_text(encoding="utf-8")
    body = source.split("def generate_latest_reports")[1]

    assert "load_previous_summary_documents(" in body
    assert '{"payload": 1, "project_id": 1, "run_id": 1, "_id": 0}' not in body
