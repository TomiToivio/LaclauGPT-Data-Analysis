"""One boundary rule for ``_id`` in Mongo writes (#553).

#515 fixed ``MongoStore.write`` and #552 fixed ``MongoTaskStore.write_result``; between them
the *class* of fault stayed open, because each writer stripped ``_id`` on its own. The rule now
lives in ``mongo_write.without_immutable_id`` and every writer calls it.

These tests pin the rule itself, the two paths that can actually receive a document pymongo
has touched, and the diagnostic that names a failing write site without quoting its message.
"""

from __future__ import annotations

from typing import Any

import pytest
from pymongo.errors import WriteError

from laclaugpt_data_analysis.distributed_worker import exception_site
from laclaugpt_data_analysis.mongo_write import without_immutable_id
from laclaugpt_data_analysis.storage import MongoStore


def test_the_immutable_id_is_removed() -> None:
    payload = {"_id": "mongo-object-id", "source_url": "https://example.invalid/1"}

    assert without_immutable_id(payload) == {"source_url": "https://example.invalid/1"}


def test_a_nested_id_is_data_and_is_preserved() -> None:
    """Only the top-level ``_id`` is MongoDB identity; a source's own id is content."""
    payload = {"source_url": "u", "source_native_ids": {"_id": "platform-own-id"}}

    assert without_immutable_id(payload)["source_native_ids"] == {"_id": "platform-own-id"}


def test_the_caller_mapping_is_not_mutated() -> None:
    payload = {"_id": "keep-me-in-the-callers-hands", "source_url": "u"}

    without_immutable_id(payload)

    assert payload["_id"] == "keep-me-in-the-callers-hands"


class _RejectingCollection:
    """A collection that refuses any ``$set`` mentioning ``_id``, like MongoDB code 66."""

    def __init__(self) -> None:
        self.written: list[dict[str, Any]] = []

    def update_one(self, identity: dict[str, Any], update: dict[str, Any], upsert: bool) -> None:
        assert "_id" not in update["$set"], "an immutable _id reached $set"
        self.written.append(dict(update["$set"]))


def test_a_row_carrying_an_id_is_written_without_it() -> None:
    """The read-then-write path: a document that came back from Mongo carries ``_id``."""
    collection = _RejectingCollection()
    store = MongoStore.__new__(MongoStore)
    store.collection = collection
    store.project_id = "ai26"

    store.write([{"_id": "from-a-read", "source_url": "https://example.invalid/1", "x": 1}])

    assert collection.written == [
        {"source_url": "https://example.invalid/1", "x": 1, "project_id": "ai26"}
    ]


def test_the_failing_site_is_named_without_the_message() -> None:
    """#553: class+code could not locate the failing write; the frame can, and is not text."""

    def write_result() -> None:
        raise WriteError("private source text must never be logged")

    with pytest.raises(WriteError) as caught:
        write_result()

    site = exception_site(caught.value)
    function, _, line = site.rpartition(":")
    assert function.endswith(":write_result")
    assert line.isdigit()
    assert "private source text" not in site


def test_a_bare_exception_has_no_site() -> None:
    assert exception_site(ValueError("no traceback")) == "unknown"
