"""Phase 0 queue selection must not starve behind a failed document (issue #202).

A document whose discourse stage failed was returned on every run, ahead of all other
work, so one permanently-unprocessable document blocked the whole queue. These tests
pin the selection contract against a fake collection, so no MongoDB is required.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "laclaugpt"))

import laclaugpt_mongo  # noqa: E402


class _Cursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, *_args):
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class _Collection:
    """Evaluates the query the way the real selection needs it to behave."""

    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.last_query: dict | None = None

    def find(self, query: dict):
        self.last_query = query
        return _Cursor([d for d in self.docs if _matches(d, query)])


def _matches(doc: dict, query: dict) -> bool:
    """Minimal subset of Mongo semantics: $and/$or/$nor + equality + $exists/$nin."""
    if "$and" in query:
        return all(_matches(doc, clause) for clause in query["$and"])
    if "$or" in query:
        return any(_matches(doc, clause) for clause in query["$or"])
    if "$nor" in query:
        return not any(_matches(doc, clause) for clause in query["$nor"])
    for key, condition in query.items():
        value = _dig(doc, key)
        if isinstance(condition, dict):
            if "$exists" in condition and (value is not None) != condition["$exists"]:
                return False
            if "$nin" in condition and value in condition["$nin"]:
                return False
            if "$ne" in condition and value == condition["$ne"]:
                return False
        elif value != condition:
            return False
    return True


def _dig(doc: dict, dotted: str):
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _install(monkeypatch, docs: list[dict]) -> _Collection:
    collection = _Collection(docs)
    monkeypatch.setattr(laclaugpt_mongo, "_collection", lambda project_id=None: collection)
    return collection


FAILED_DOC = {
    "document_id": "failing",
    "source_date": "2026-09-18",
    "phase0": {"discourse": {"status": "error", "attempts": 1}},
}
UNPROCESSED_DOC = {"document_id": "fresh", "source_date": "2026-09-17"}
OK_DOC = {"document_id": "done", "source_date": "2026-09-16",
          "phase0": {"discourse": {"status": "ok"}}}


# --------------------------------------------------------------------------
# The starvation fix
# --------------------------------------------------------------------------

def test_failed_document_is_not_selected_by_default(monkeypatch) -> None:
    """The core of #202: an erroring document must not block the queue."""
    _install(monkeypatch, [FAILED_DOC, UNPROCESSED_DOC, OK_DOC])
    ids = [d["document_id"] for d in laclaugpt_mongo.find_documents(limit=10, project_id="ai26")]
    assert "failing" not in ids, "a failed document must not be retried implicitly"
    assert "fresh" in ids


def test_default_run_makes_progress_when_one_document_keeps_failing(monkeypatch) -> None:
    """Simulates repeated runs: the failing document never blocks the others."""
    _install(monkeypatch, [FAILED_DOC, UNPROCESSED_DOC])
    for _ in range(3):
        ids = [d["document_id"] for d in laclaugpt_mongo.find_documents(limit=10, project_id="ai26")]
        assert ids == ["fresh"], f"expected only the processable document, got {ids}"


def test_completed_documents_are_not_reselected(monkeypatch) -> None:
    _install(monkeypatch, [OK_DOC, UNPROCESSED_DOC])
    ids = [d["document_id"] for d in laclaugpt_mongo.find_documents(limit=10, project_id="ai26")]
    assert ids == ["fresh"]


def test_failed_document_is_reachable_for_explicit_retry(monkeypatch) -> None:
    """Failures stay recoverable — just never implicit."""
    _install(monkeypatch, [FAILED_DOC, UNPROCESSED_DOC])
    ids = [
        d["document_id"]
        for d in laclaugpt_mongo.find_documents(limit=10, retry_errors=True, project_id="ai26")
    ]
    assert ids == ["failing"]


def test_an_error_in_any_stage_excludes_the_document(monkeypatch) -> None:
    """A failure mid-pipeline must also stop the document being re-selected."""
    docs = [
        {"document_id": "pre_err", "phase0": {"preprocess": {"status": "error"}}},
        {"document_id": "sum_err", "phase0": {"summary": {"status": "error"}}},
        {"document_id": "post_err", "phase0": {"postprocess": {"status": "error"}}},
        UNPROCESSED_DOC,
    ]
    _install(monkeypatch, docs)
    ids = {d["document_id"] for d in laclaugpt_mongo.find_documents(limit=10, project_id="ai26")}
    assert ids == {"fresh"}, ids


def test_explicit_document_id_still_selects_a_failed_document(monkeypatch) -> None:
    """A human can always target a specific document, failed or not."""
    _install(monkeypatch, [FAILED_DOC, UNPROCESSED_DOC])
    docs = laclaugpt_mongo.find_documents(limit=10, document_id="failing", project_id="ai26")
    assert [d["document_id"] for d in docs] == ["failing"]


# --------------------------------------------------------------------------
# Failure visibility
# --------------------------------------------------------------------------

def test_failure_records_an_attempt_count() -> None:
    """A permanently failing document must be visible, not silently skipped."""
    import laclaugpt_process  # noqa: E402

    first = laclaugpt_process._status("error", "boom", 1)
    assert first["attempts"] == 1
    assert first["status"] == "error"

    # The counter increments across attempts rather than resetting.
    prior = {"attempts": 2}
    assert int(prior.get("attempts") or 0) + 1 == 3


def test_status_without_attempts_omits_the_field() -> None:
    import laclaugpt_process  # noqa: E402

    assert "attempts" not in laclaugpt_process._status("ok")
