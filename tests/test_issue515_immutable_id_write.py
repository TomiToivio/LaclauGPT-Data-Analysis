"""#515: an immutable ``_id`` must never reach a ``$set``, because it discards finished work.

The failure that motivated this file, from a bounded cycle on Laskin (2026-11-22 17:03 EET):

```
WriteError: After applying the update, the (immutable) field '_id' was found to have been altered
             ... full error: {'index': 0, 'code': 66, ...}
{'completed': 0, 'retry': 1, ...} failure_classes={'WriteError': 1}
```

The model had done the work and the result was thrown away. Three such failures were recorded that day
(14:42, 14:56, 15:03). ``read()`` strips ``_id`` so a reader cannot leak it; ``write()`` did not, so a row
carrying one — from a read, or from a stage that passed the document through — produced a ``$set`` containing
``_id`` and MongoDB refused the whole update.
"""

from __future__ import annotations

from typing import Any

from laclaugpt_data_analysis.storage import MongoStore


class _RecordingCollection:
    """Minimal stand-in that records the update a store attempts."""

    def __init__(self) -> None:
        self.updates: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def update_one(self, identity, update, upsert=False):  # noqa: ANN001, ANN201, ARG002
        self.updates.append((dict(identity), dict(update)))

    def find(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201, ARG002
        return []


def test_an_id_in_the_row_is_not_written_back():
    collection = _RecordingCollection()
    store = MongoStore.__new__(MongoStore)
    store.collection = collection
    store.project_id = "ai26"

    store.write([{"_id": "6b030455821a4e578bdb238d", "source_url": "https://example.test/a", "x": 1}])

    identity, update = collection.updates[0]
    assert "_id" not in update["$set"], "an immutable field in $set is WriteError code 66"
    assert update["$set"]["x"] == 1
    assert update["$set"]["project_id"] == "ai26"
    assert identity == {"project_id": "ai26", "source_url": "https://example.test/a"}


def test_a_row_without_an_id_is_unchanged():
    collection = _RecordingCollection()
    store = MongoStore.__new__(MongoStore)
    store.collection = collection
    store.project_id = "ai26"

    store.write([{"source_url": "https://example.test/b", "y": 2}])

    _, update = collection.updates[0]
    assert update["$set"] == {"source_url": "https://example.test/b", "y": 2, "project_id": "ai26"}
