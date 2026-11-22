"""A re-analysed result must be replaceable without an immutable-``_id`` WriteError.

Live failure this pins (Laskin, 2026-11-22 19:10 and 19:16 EET), from the stored failure documents:

```
WriteError: After applying the update, the (immutable) field '_id' was found to have been altered
             to _id: ObjectId('6b0321f7acebe0ad53437719') ... 'code': 66
```

The cycle reported ``claims: 9, completed: 0, retry: 9``: every finished analysis was thrown away and
then re-run against the model.

Mechanism: pymongo adds ``_id`` to the *caller's* document dict while encoding an insert, and it does
so before the server rejects a duplicate key. ``MongoTaskStore.write_result`` then reused that same
dict as the ``replace_one`` replacement, so the replacement carried a freshly generated ``_id`` that
differed from the stored document's — and MongoDB refuses a replacement that alters ``_id`` (code 66).

This is the same class of fault as #515 (``MongoStore.write`` sending ``_id`` in ``$set``), in a second
write path. The fakes below reproduce pymongo's mutation and MongoDB's refusal; if the store stops
passing a copy or stops stripping ``_id``, these tests fail with the error the operator saw.
"""

from __future__ import annotations

from typing import Any

import pytest
from pymongo.errors import DuplicateKeyError, WriteError

from laclaugpt_data_analysis.task_queue.models import TaskEnvelope
from laclaugpt_data_analysis.task_queue.mongo_store import MongoTaskStore

IMMUTABLE_FIELD_ERROR = 66


class FakeResultCollection:
    """Just enough of a pymongo collection to reproduce the immutable-``_id`` refusal."""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.replacements: list[dict[str, Any]] = []

    def insert_one(self, document: dict[str, Any]) -> None:
        stored = self.documents.get(str(document["idempotency_key"]))
        # pymongo encodes ``_id`` into the caller's dict before the server sees the command, so a
        # rejected insert still leaves the dict mutated. That mutation is the bug's whole fuel.
        document.setdefault("_id", f"generated-{len(self.documents) + 1}")
        if stored is not None:
            raise DuplicateKeyError("E11000 duplicate key error collection: ai26.analysis_results")
        self.documents[str(document["idempotency_key"])] = dict(document)

    def find_one(self, query: dict[str, Any], projection: dict[str, Any] | None = None) -> Any:
        document = self.documents.get(str(query["idempotency_key"]))
        if document is None:
            return None
        if projection and projection.get("_id") == 0:
            return {key: value for key, value in document.items() if key != "_id"}
        return dict(document)

    def replace_one(self, query: dict[str, Any], replacement: dict[str, Any]) -> None:
        stored = self.documents.get(str(query["idempotency_key"]))
        assert stored is not None
        if "_id" in replacement and replacement["_id"] != stored["_id"]:
            raise WriteError(
                "After applying the update, the (immutable) field '_id' was found to have been "
                f"altered to _id: {replacement['_id']}, full error: {{'index': 0, 'code': "
                f"{IMMUTABLE_FIELD_ERROR}}}"
            )
        self.replacements.append(dict(replacement))
        self.documents[str(query["idempotency_key"])] = {**replacement, "_id": stored["_id"]}


def make_store(collection: FakeResultCollection) -> MongoTaskStore:
    """A store wired to the fake, without a live Mongo client or index creation."""
    store = MongoTaskStore.__new__(MongoTaskStore)
    store.results = collection  # type: ignore[assignment]
    store.failures = collection  # type: ignore[assignment]
    store.project_id = "ai26"
    store.run_id = "ai26-distributed-001"
    return store


def make_task() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task-1",
        idempotency_key="idem-1",
        project_id="ai26",
        run_id="ai26-distributed-001",
        task_type="analysis",
        record_ref="https://example.invalid/article/1",
        schema_version="1.2.0",
        config_revision="cfg-1",
        codebook_revision="cb-1",
    )


def test_a_reanalysis_replaces_the_stored_result_instead_of_raising() -> None:
    """The second write for one source is the duplicate path — the one that failed live."""
    collection = FakeResultCollection()
    store = make_store(collection)

    assert store.write_result(
        make_task(), {"summary": "first"}, {"model": "gemma4:12b"}, fingerprint="fp-1"
    )
    assert (
        store.write_result(
            make_task(), {"summary": "second"}, {"model": "gemma4:12b"}, fingerprint="fp-2"
        )
        is True
    )

    assert collection.documents["idem-1"]["result"] == {"summary": "second"}
    assert len(collection.replacements) == 1
    assert "_id" not in collection.replacements[0], (
        "the replacement must not carry _id: MongoDB refuses a replacement that alters it (code 66)"
    )


def test_the_stored_identity_survives_the_replacement() -> None:
    collection = FakeResultCollection()
    store = make_store(collection)

    store.write_result(
        make_task(), {"summary": "first"}, {"model": "gemma4:12b"}, fingerprint="fp-1"
    )
    original_id = collection.documents["idem-1"]["_id"]
    store.write_result(
        make_task(), {"summary": "second"}, {"model": "gemma4:12b"}, fingerprint="fp-2"
    )

    assert collection.documents["idem-1"]["_id"] == original_id


def test_an_unchanged_fingerprint_is_a_duplicate_and_never_replaces() -> None:
    collection = FakeResultCollection()
    store = make_store(collection)

    store.write_result(
        make_task(), {"summary": "first"}, {"model": "gemma4:12b"}, fingerprint="fp-1"
    )
    assert (
        store.write_result(
            make_task(), {"summary": "second"}, {"model": "gemma4:12b"}, fingerprint="fp-1"
        )
        is False
    )
    assert collection.replacements == []
    assert collection.documents["idem-1"]["result"] == {"summary": "first"}


@pytest.mark.parametrize("fingerprint", ["", "fp-1", "fp-2"])
def test_every_fingerprint_path_can_persist(fingerprint: str) -> None:
    """No fingerprint configuration may turn a finished analysis into a WriteError."""
    collection = FakeResultCollection()
    store = make_store(collection)

    assert store.write_result(
        make_task(), {"summary": "x"}, {"model": "m"}, fingerprint=fingerprint
    )
    assert collection.documents["idem-1"]["generation_fingerprint"] == fingerprint
