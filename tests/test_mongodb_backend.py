from __future__ import annotations

from dataclasses import replace

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.mongodb_rag import MongoRetrievalBackend, _cosine
from laclaugpt_data_analysis.storage import resolved_storage_backend


class FakeCursor(list):
    def limit(self, n):
        return FakeCursor(self[:n])


class FakeCollection:
    def __init__(self, name):
        self.name = name
        self.rows = []
    def create_index(self, *args, **kwargs): return "idx"
    def update_one(self, query, update, upsert=False):
        payload = dict(update.get("$set") or {})
        existing = next((row for row in self.rows if row.get("canonical_id") == query.get("canonical_id")), None)
        if existing is None: self.rows.append(payload)
        else: existing.update(payload)
    def delete_many(self, query):
        if "source_record" in query:
            self.rows[:] = [row for row in self.rows if row.get("source_record") != query["source_record"]]
        elif query.get("rag_managed") is True:
            self.rows[:] = [row for row in self.rows if row.get("rag_managed") is not True]
    def insert_many(self, rows): self.rows.extend(dict(row) for row in rows)
    def find_one(self, query):
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()): return dict(row)
        return None
    def find(self, query=None):
        query = query or {}
        def matches(row):
            for key, value in query.items():
                if key == "$or":
                    if not any(matches_clause(row, clause) for clause in value): return False
                elif isinstance(value, dict) and "$type" in value:
                    if value["$type"] == "array" and not isinstance(row.get(key), list): return False
                elif row.get(key) != value: return False
            return True
        def matches_clause(row, clause):
            for key, value in clause.items():
                if isinstance(value, dict) and "$in" in value:
                    if row.get(key) not in value["$in"]: return False
                elif row.get(key) != value: return False
            return True
        return FakeCursor([dict(row) for row in self.rows if matches(row)])
    def aggregate(self, pipeline): return []


class FakeDatabase:
    def __init__(self): self.collections = {}
    def __getitem__(self, name): return self.collections.setdefault(name, FakeCollection(name))
    def command(self, command):
        if command == "ping": return {"ok": 1}
        raise RuntimeError("no search indexes")


class FakeEmbedding:
    model = "multilingual-test"
    def embed(self, texts): return [[float(len(text)), 1.0] for text in texts]


def test_cosine_similarity_is_portable():
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_storage_csv_never_requires_mongodb(monkeypatch, tmp_path):
    monkeypatch.setattr("laclaugpt_data_analysis.storage._mongodb_reachable", lambda settings: (_ for _ in ()).throw(AssertionError("must not probe")))
    settings = Settings(storage_backend="csv", data_dir=tmp_path, mongo_url="mongodb://secret.invalid")
    assert resolved_storage_backend(settings) == "csv"


def test_auto_falls_back_to_csv_when_mongodb_unreachable(monkeypatch, tmp_path):
    monkeypatch.setattr("laclaugpt_data_analysis.storage._mongodb_reachable", lambda settings: False)
    settings = Settings(storage_backend="auto", data_dir=tmp_path, mongo_url="mongodb://unreachable.invalid")
    assert resolved_storage_backend(settings) == "csv"


def test_explicit_mongodb_fails_when_unreachable(monkeypatch):
    monkeypatch.setattr("laclaugpt_data_analysis.storage._mongodb_reachable", lambda settings: False)
    with pytest.raises(ConnectionError, match="required but unavailable"):
        resolved_storage_backend(Settings(storage_backend="mongodb", mongo_url="mongodb://unreachable.invalid"))


def test_mongodb_index_persists_embedding_reproducibility_metadata():
    database = FakeDatabase()
    backend = MongoRetrievalBackend(database=database, project_id="ai26", embedding_provider=FakeEmbedding())
    record = CanonicalRecord(source_url="https://example.org/1")
    record.content.text = "AI regulation and labour"
    record.source.platform = "rss"
    record.source.raw_metadata.update({"collection_id": "AI26", "arena": "parliamentary"})
    assert backend.index_records([record]) == 1
    row = database["ai26__rag_records"].find_one({"canonical_id": record.source_url})
    assert row["dataset"] == "AI26"
    assert row["arena"] == "parliamentary"
    assert row["embedding_metadata"]["model"] == "multilingual-test"
    assert row["embedding_metadata"]["dimensions"] == 2
    assert len(row["embedding_metadata"]["source_text_sha256"]) == 64


def test_mongodb_vector_search_degrades_without_native_index():
    database = FakeDatabase()
    backend = MongoRetrievalBackend(database=database, project_id="ai26", embedding_provider=FakeEmbedding())
    first = CanonicalRecord(source_url="https://example.org/1"); first.content.text = "AI"
    second = CanonicalRecord(source_url="https://example.org/2"); second.content.text = "AI governance and democratic control"
    backend.index_records([first, second])
    items = backend.vector_search("AI governance", top_k=1)
    assert len(items) == 1
    assert items[0].metadata["embedding_metadata"]["model"] == "multilingual-test"


def test_storage_backend_setting_is_independent_of_legacy_data_backend():
    settings = Settings(storage_backend="csv", data_backend="mongodb", mongo_url="mongodb://example.invalid")
    assert replace(settings, data_backend="sqlite").storage_backend == "csv"
