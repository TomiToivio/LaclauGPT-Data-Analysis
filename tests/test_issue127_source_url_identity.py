from __future__ import annotations

import sys
import types

from laclaugpt_data_analysis.task_queue import MongoTaskStore, TaskEnvelope


def _task() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="analysis:demo",
        idempotency_key="demo",
        project_id="ai26",
        run_id="run-1",
        task_type="analyze-record",
        record_ref="https://example.org/source/1",
        schema_version="1.0",
        config_revision="cfg",
        codebook_revision="cb",
    )


class FakeCollection:
    def __init__(self) -> None:
        self.documents: list[dict] = []
        self.indexes: list[tuple] = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def find_one(self, query, projection=None):
        del projection
        for row in self.documents:
            if all(row.get(key) == value for key, value in query.items()):
                return row
        return None

    def insert_one(self, document):
        self.documents.append(dict(document))
        return object()


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


class FakeClient:
    databases: dict[str, FakeDatabase] = {}

    def __init__(self, url: str):
        self.url = url

    def __getitem__(self, name: str) -> FakeDatabase:
        return self.databases.setdefault(name, FakeDatabase())


def _store(monkeypatch) -> MongoTaskStore:
    FakeClient.databases.clear()
    pymongo = types.ModuleType("pymongo")
    pymongo.MongoClient = FakeClient
    errors = types.ModuleType("pymongo.errors")

    class DuplicateKeyError(Exception):
        pass

    errors.DuplicateKeyError = DuplicateKeyError
    monkeypatch.setitem(sys.modules, "pymongo", pymongo)
    monkeypatch.setitem(sys.modules, "pymongo.errors", errors)
    return MongoTaskStore(
        "mongodb://example.invalid",
        database="laclaugpt",
        result_collection="ai26__analysis_results",
        failure_collection="ai26__analysis_failures",
        project_id="ai26",
        run_id="run-1",
    )


def test_mongo_result_persists_source_url(monkeypatch):
    store = _store(monkeypatch)
    task = _task()

    assert store.write_result(task, {"source_url": task.record_ref}, {"worker": "test"})

    row = store.results.documents[0]
    assert row["source_url"] == task.record_ref
    assert row["result"]["source_url"] == task.record_ref


def test_mongo_failure_persists_source_url_once(monkeypatch):
    store = _store(monkeypatch)
    task = _task()

    store.write_failure(task, "boom", {"worker": "test"})

    row = store.failures.documents[0]
    assert row["source_url"] == task.record_ref
    assert row["error"] == "boom"
    assert list(row).count("source_url") == 1
