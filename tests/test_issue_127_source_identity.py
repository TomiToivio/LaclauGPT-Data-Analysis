from laclaugpt_data_analysis.task_queue import MongoTaskStore, TaskEnvelope


class FakeCollection:
    def __init__(self):
        self.indexes = []
        self.inserted = []

    def create_index(self, fields, **kwargs):
        self.indexes.append((fields, kwargs))
        return kwargs.get("name")

    def find_one(self, *args, **kwargs):
        return None

    def insert_one(self, document):
        self.inserted.append(document)
        return object()


def _store_without_pymongo_init():
    store = object.__new__(MongoTaskStore)
    store.results = FakeCollection()
    store.failures = FakeCollection()
    store.project_id = "ai26"
    store.run_id = "run-001"
    return store


def test_mongo_result_persists_canonical_source_url_at_top_level(monkeypatch):
    store = _store_without_pymongo_init()

    class DuplicateKeyError(Exception):
        pass

    monkeypatch.setitem(__import__("sys").modules, "pymongo.errors", type("E", (), {"DuplicateKeyError": DuplicateKeyError}))

    source_url = "https://example.invalid/source/1"
    assert store.write_result(
        "handoff-1",
        {"source_url": source_url, "floating_signifiers": ["AI"]},
        {"worker_id": "worker-1"},
    )

    document = store.results.inserted[0]
    assert document["source_url"] == source_url
    assert document["result"]["source_url"] == source_url
    assert document["project_id"] == "ai26"
    assert document["run_id"] == "run-001"


def test_mongo_result_rejects_missing_source_url(monkeypatch):
    store = _store_without_pymongo_init()

    class DuplicateKeyError(Exception):
        pass

    monkeypatch.setitem(__import__("sys").modules, "pymongo.errors", type("E", (), {"DuplicateKeyError": DuplicateKeyError}))

    try:
        store.write_result("handoff-1", {"floating_signifiers": ["AI"]}, {})
    except ValueError as exc:
        assert "source_url" in str(exc)
    else:
        raise AssertionError("missing canonical source_url must fail loudly")


def test_processing_failure_persists_task_record_ref_as_source_url():
    store = _store_without_pymongo_init()
    source_url = "https://example.invalid/source/1"
    task = TaskEnvelope(
        task_id="analysis:handoff-1",
        idempotency_key="handoff-1",
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref=source_url,
        schema_version="1",
        config_revision="cfg",
        codebook_revision="cb",
    )

    store.write_failure(task, "RuntimeError: boom", {"worker_id": "worker-1"})

    document = store.failures.inserted[0]
    assert document["source_url"] == source_url
    assert document["project_id"] == "ai26"
    assert document["run_id"] == "run-001"
