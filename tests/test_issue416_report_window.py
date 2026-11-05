"""The periodic report got slower as the corpus grew, and then hit its ceiling (#416).

The report loaded **every** analysis result in the run and validated each one with pydantic, and only
then filtered by the window it was going to summarise. Validation dominated: five ceiling events in
14 hours, on windows that contained a fraction of the corpus.

The fix is to decide *which* records are in the window before decoding them — read two timestamp fields
from the projection, collect the ids, then validate only those. This test pins both halves: the cheap
first pass, the narrow second pass, and the fact that the timestamps used are the same ones the summary
itself uses, so the two cannot disagree about what belongs in a window.

It also pins the grading half: a worker cycle that did its work and only lost its report must not be
graded as a failed cycle.
"""
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laclaugpt_data_analysis import phase1_laskin_report as report  # noqa: E402


class _Cursor(list):
    pass


class _Collection:
    def __init__(self, documents):
        self.documents = documents
        self.calls = []

    def find(self, query, projection=None):
        self.calls.append((dict(query), dict(projection or {})))
        if "_id" in query:
            wanted = set(query["_id"]["$in"])
            return _Cursor(doc for doc in self.documents if doc["_id"] in wanted)
        return _Cursor(self.documents)


class _Database:
    def __init__(self, collection):
        self._collection = collection

    def __getitem__(self, _name):
        return self._collection


class _Client:
    def __init__(self, collection):
        self._database = _Database(collection)

    def __getitem__(self, _name):
        return self._database


def _document(index: int, created: str | None, *, collected: str | None = None):
    source = {}
    if created is not None:
        source["created_at"] = created
    if collected is not None:
        source["collected_at"] = collected
    return {"_id": index, "result": {"source": source, "content": {"text": "x"}}}


def _settings():
    class _Namespace:
        def mongo_collection(self, name):
            return f"ai26__{name}"

    class _Settings:
        project_id = "ai26"
        mongo_database = "spectra"
        distributed_namespace = _Namespace()

    return _Settings()


def test_the_window_is_decided_before_any_record_is_validated(monkeypatch):
    documents = [
        _document(1, "2026-11-02T10:00:00Z"),
        _document(2, "2026-11-02T11:30:00Z"),
        _document(3, "2026-11-03T02:00:00Z"),   # outside the window
        _document(4, None, collected="2026-11-02T12:00:00Z"),  # timestamp falls back to collected_at
        _document(5, None),                      # no timestamp at all
    ]
    collection = _Collection(documents)
    monkeypatch.setattr(report, "_mongo_client", lambda _settings: _Client(collection))
    validated = []
    original = report._decode_result

    def counting_decode(document):
        validated.append(document["_id"])
        return original(document)

    monkeypatch.setattr(report, "_decode_result", counting_decode)

    start = datetime(2026, 11, 2, 10, tzinfo=UTC)
    end = start + timedelta(hours=4)
    report.load_analysis_records(_settings(), run_id="ai26-distributed-001", window=(start, end))

    assert len(collection.calls) == 2
    first_query, first_projection = collection.calls[0]
    assert first_query == {"project_id": "ai26", "run_id": "ai26-distributed-001"}
    assert set(first_projection) == {"result.source.created_at", "result.source.collected_at"}
    assert "_id" in collection.calls[1][0]
    # Only in-window documents (by created_at, or collected_at when created_at is absent) reach pydantic.
    assert sorted(validated) == [1, 2, 4]


def test_a_window_with_no_matches_does_not_run_a_second_query(monkeypatch):
    collection = _Collection([_document(1, "2026-01-01T00:00:00Z")])
    monkeypatch.setattr(report, "_mongo_client", lambda _settings: _Client(collection))

    start = datetime(2026, 11, 2, 10, tzinfo=UTC)
    assert report.load_analysis_records(
        _settings(), run_id="run", window=(start, start + timedelta(hours=1))
    ) == []
    assert len(collection.calls) == 1


def test_without_a_window_the_old_behaviour_is_unchanged(monkeypatch):
    collection = _Collection([_document(1, "2026-01-01T00:00:00Z")])
    monkeypatch.setattr(report, "_mongo_client", lambda _settings: _Client(collection))
    report.load_analysis_records(_settings(), run_id="run")
    assert len(collection.calls) == 1
    assert collection.calls[0][1] == {"result": 1, "_id": 0}


def test_a_report_timeout_is_graded_apart_from_a_worker_failure():
    """The exit-code contract, read from the wrapper that implements it."""
    script = (ROOT / "scripts" / "run_ai26_laskin.sh").read_text(encoding="utf-8")
    assert "REPORT_DEGRADED=1" in script
    assert 'REPORT_STATUS" -eq 124 || "$REPORT_STATUS" -eq 137' in script
    # The degraded branch must not set the failure status, and the failure branch must still exist.
    degraded = script.split("REPORT_DEGRADED=1")[1]
    assert "FINAL_STATUS=4" not in degraded.split("fi")[0]
    assert "FINAL_STATUS=4" in script
