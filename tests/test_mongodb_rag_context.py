from __future__ import annotations

from copy import deepcopy

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.context_orchestration import (
    AnalysisContextPolicy,
    assemble_analysis_context,
)
from laclaugpt_data_analysis.mongodb_rag import MongoRetrievalBackend
from laclaugpt_data_analysis.rag import NullRetrievalBackend


class FakeCursor(list):
    def limit(self, value: int):
        return FakeCursor(self[:value])


class FakeCollection:
    def __init__(self, name: str):
        self.name = name
        self.documents: list[dict] = []

    def create_index(self, *args, **kwargs):
        return kwargs.get("name", "index")

    @staticmethod
    def _matches(document: dict, query: dict) -> bool:
        for key, expected in query.items():
            if key == "$or":
                if not any(FakeCollection._matches(document, item) for item in expected):
                    return False
                continue
            if isinstance(expected, dict):
                if "$type" in expected:
                    if expected["$type"] == "array" and not isinstance(document.get(key), list):
                        return False
                    continue
                if "$in" in expected:
                    if document.get(key) not in expected["$in"]:
                        return False
                    continue
            if document.get(key) != expected:
                return False
        return True

    def update_one(self, query: dict, update: dict, *, upsert: bool = False):
        for document in self.documents:
            if self._matches(document, query):
                document.update(deepcopy(update.get("$set", {})))
                return
        if upsert:
            value = deepcopy(query)
            value.update(deepcopy(update.get("$set", {})))
            self.documents.append(value)

    def delete_many(self, query: dict):
        self.documents = [doc for doc in self.documents if not self._matches(doc, query)]

    def insert_many(self, values: list[dict]):
        self.documents.extend(deepcopy(values))

    def find(self, query: dict | None = None):
        query = query or {}
        return FakeCursor([deepcopy(doc) for doc in self.documents if self._matches(doc, query)])

    def find_one(self, query: dict):
        for document in self.documents:
            if self._matches(document, query):
                return deepcopy(document)
        return None

    def aggregate(self, pipeline):
        raise AssertionError("native vector search is not used in this fixture")


class FakeDatabase:
    def __init__(self):
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str):
        return self.collections.setdefault(name, FakeCollection(name))

    def command(self, command):
        if command == "ping":
            return {"ok": 1}
        if isinstance(command, dict) and "listSearchIndexes" in command:
            return {"cursor": {"firstBatch": []}}
        return {"ok": 1}


def _record(url: str, text: str, *, project: str = "AI26") -> CanonicalRecord:
    record = CanonicalRecord(source_url=url)
    record.content.text = text
    record.source.raw_metadata["collection_id"] = project
    return record


def test_small_indexed_mongodb_corpus_is_retrieved_as_context_not_evidence() -> None:
    database = FakeDatabase()
    backend = MongoRetrievalBackend(database=database, project_id="AI26")
    records = [
        _record("https://example.org/current", "Current item about AI regulation"),
        _record("https://example.org/related-1", "AI regulation and independent evaluation"),
        _record("https://example.org/related-2", "Labour and ownership in AI systems"),
    ]
    assert backend.index_records(records) == 3

    current = records[0]
    policy = AnalysisContextPolicy()
    policy.stages["discourse"].rag_mode = "graph"
    bundle, adapter = assemble_analysis_context(
        current,
        project_id="AI26",
        stage="discourse",
        task="Analyse the current source.",
        policy=policy,
        retrieval_backend=backend,
    )

    assert "AI regulation and independent evaluation" in bundle.rag_context.text
    assert "RAG RETRIEVAL CONTEXT" in bundle.rag_context.text
    assert "NOT CURRENT-SOURCE EVIDENCE" in bundle.rag_context.text
    assert "https://example.org/current" not in bundle.rag_context.record_ids
    assert bundle.rag_context.evidence_role == "context"
    assert bundle.current_source.evidence_role == "source_evidence"
    assert adapter.rag_context == bundle.rag_context.text

    rag_sources = bundle.provenance["rag"]["sources"]
    assert rag_sources
    assert rag_sources[0]["source"] == "rag:MongoRetrievalBackend"
    assert rag_sources[0]["metadata"]["evidence_role"] == "context"
    assert rag_sources[0]["metadata"]["retrieval_method"] == "graph"


def test_disabled_rag_is_prompt_equivalent_to_no_retrieval_backend() -> None:
    record = _record("https://example.org/current", "Current source evidence")
    policy = AnalysisContextPolicy()

    without_backend, _ = assemble_analysis_context(
        record,
        project_id="AI26",
        stage="discourse",
        task="Analyse the current source.",
        policy=policy,
        retrieval_backend=None,
    )
    disabled_backend, _ = assemble_analysis_context(
        record,
        project_id="AI26",
        stage="discourse",
        task="Analyse the current source.",
        policy=policy,
        retrieval_backend=NullRetrievalBackend(),
    )

    without_prompt = without_backend.prompt_envelope(record, prompt_version="test-v1").render()
    disabled_prompt = disabled_backend.prompt_envelope(record, prompt_version="test-v1").render()

    assert without_prompt == disabled_prompt
    assert without_backend.rag_context.text == ""
    assert disabled_backend.rag_context.text == ""
    assert without_backend.provenance["rag_audit"]["status"] == "disabled"
    assert disabled_backend.provenance["rag_audit"]["status"] == "disabled"
