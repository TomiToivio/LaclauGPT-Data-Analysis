import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LACLAUGPT_DIR = ROOT / "laclaugpt"
if str(LACLAUGPT_DIR) not in sys.path:
    sys.path.insert(0, str(LACLAUGPT_DIR))

import laclaugpt_mongo


class FakeCursor:
    def __init__(self):
        self.sort_args = None
        self.limit_value = None

    def sort(self, *args):
        self.sort_args = args
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def __iter__(self):
        return iter([])


class FakeCollection:
    def __init__(self):
        self.find_query = None
        self.cursor = FakeCursor()
        self.updates = []

    def find(self, query):
        self.find_query = query
        return self.cursor

    def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))


def test_default_find_documents_excludes_error_documents(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(laclaugpt_mongo, "_collection", lambda project_id=None: collection)

    laclaugpt_mongo.find_documents(limit=5, project_id="ai26")

    assert collection.find_query == {"phase0.discourse.status": {"$exists": False}}
    assert collection.cursor.limit_value == 5


def test_retry_errors_explicitly_selects_failed_documents(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(laclaugpt_mongo, "_collection", lambda project_id=None: collection)

    laclaugpt_mongo.find_documents(retry_errors=True, project_id="ai26")

    assert collection.find_query == {
        "$or": [
            {"phase0.preprocess.status": "error"},
            {"phase0.summary.status": "error"},
            {"phase0.postprocess.status": "error"},
            {"phase0.discourse.status": "error"},
        ]
    }


def test_record_stage_failure_increments_attempts_and_sets_failure_times(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(laclaugpt_mongo, "_collection", lambda project_id=None: collection)

    laclaugpt_mongo.record_stage_failure(
        {"source_url": "https://example.com/doc"},
        "discourse",
        "broken output",
        project_id="ai26",
    )

    assert len(collection.updates) == 2
    query, update, upsert = collection.updates[0]
    assert query == {"source_url": "https://example.com/doc"}
    assert upsert is True
    assert update["$inc"] == {"phase0.discourse.attempt_count": 1}
    assert update["$set"]["phase0.discourse.status"] == "error"
    assert update["$set"]["phase0.discourse.error"] == "broken output"
    assert "phase0.discourse.last_failure_at" in update["$set"]
    assert "phase0.discourse.first_failure_at" in update["$setOnInsert"]

    second_query, second_update, second_upsert = collection.updates[1]
    assert second_query == {
        "source_url": "https://example.com/doc",
        "phase0.discourse.first_failure_at": {"$exists": False},
    }
    assert "phase0.discourse.first_failure_at" in second_update["$set"]
    assert second_upsert is False
