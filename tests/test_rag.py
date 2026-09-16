from __future__ import annotations

from dataclasses import replace

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.rag import (
    Neo4jRetrievalBackend,
    NullRetrievalBackend,
    RetrievalItem,
    _context,
    backend_from_settings,
    failed_context,
    record_filters,
)


class FakeEmbedding:
    model = "multilingual-test-embed"

    def embed(self, texts):
        return [[float(len(text)), 0.25] for text in texts]


class FakeResult(list):
    pass


class FakeSession:
    def __init__(self, driver):
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, cypher, params):
        self.driver.calls.append((cypher, dict(params)))
        if "db.index.vector.queryNodes" in cypher:
            return FakeResult(
                [
                    {
                        "canonical_id": "https://example.org/vector",
                        "text": "vector context",
                        "score": 0.91,
                        "dataset": "AI26",
                        "arena": "elites",
                        "country": "FI",
                    }
                ]
            )
        if "OPTIONAL MATCH p=" in cypher:
            return FakeResult(
                [
                    {
                        "canonical_id": "https://example.org/graph",
                        "text": "graph context",
                        "path": ["https://example.org/graph", "AI", "frontier"],
                        "dataset": "AI26",
                        "arena": "elites",
                        "country": "FI",
                    }
                ]
            )
        return FakeResult()


class FakeDriver:
    def __init__(self, *, healthy=True):
        self.healthy = healthy
        self.calls = []

    def verify_connectivity(self):
        if not self.healthy:
            raise OSError("offline")

    def session(self, database=None):
        assert database == "neo4j"
        return FakeSession(self)


def backend(*, healthy=True):
    return Neo4jRetrievalBackend(
        uri="bolt://example.invalid:7687",
        user="neo4j",
        password="private",
        embedding_provider=FakeEmbedding(),
        driver=FakeDriver(healthy=healthy),
    )


def test_rag_disabled_is_explicit_noop():
    rag = backend_from_settings(Settings(rag_enabled=False))
    assert isinstance(rag, NullRetrievalBackend)
    context = rag.retrieve_context("query", mode="none")
    assert context.items == []
    assert context.audit.status == "disabled"


def test_unavailable_neo4j_healthcheck_and_failure_audit_hide_endpoint():
    rag = backend(healthy=False)
    assert rag.healthcheck() is False
    context = failed_context(
        method="hybrid",
        filters={"dataset": "AI26"},
        embedding_model="embed",
        error=OSError("bolt://secret-host:7687 failed"),
    )
    assert context.audit.status == "unavailable"
    assert "secret-host" not in context.audit.warning


def test_vector_graph_and_hybrid_retrieval_keep_provenance_and_filters():
    rag = backend()
    filters = {"dataset": "AI26", "country": "FI", "arena": "elites"}

    vector = rag.retrieve_context("AI future", filters, mode="vector", top_k=3)
    assert vector.audit.method == "vector"
    assert vector.audit.filters == filters
    assert vector.audit.embedding_model == "multilingual-test-embed"
    assert vector.items[0].score == pytest.approx(0.91)

    graph = rag.retrieve_context("AI future", filters, mode="graph", top_k=3, depth=3)
    assert graph.audit.method == "graph"
    assert graph.items[0].graph_path[-1] == "frontier"
    assert graph.audit.graph_paths["https://example.org/graph"][-1] == "frontier"

    hybrid = rag.retrieve_context("AI future", filters, mode="hybrid", top_k=5)
    assert hybrid.audit.selected_canonical_ids == [
        "https://example.org/vector",
        "https://example.org/graph",
    ]
    assert hybrid.audit.context_size > 0


def test_metadata_filters_are_parameterized_not_interpolated():
    rag = backend()
    rag.vector_search(
        "query",
        {"dataset": "AI26' MATCH (n) DETACH DELETE n //", "platform": "x"},
        top_k=2,
    )
    cypher, params = rag.driver.calls[-1]
    assert "DETACH DELETE" not in cypher
    assert params["filter_dataset"].startswith("AI26'")
    assert params["filter_platform"] == "x"


def test_indexing_uses_merge_and_rebuild_is_canonical():
    rag = backend()
    record = CanonicalRecord(source_url="https://example.org/1")
    record.content.text = "AI governance"
    record.source.platform = "x"
    record.source.country = "FI"
    record.source.raw_metadata.update({"collection_id": "AI26", "arena": "parliamentary"})

    assert rag.index_records([record]) == 1
    write_query, params = rag.driver.calls[0]
    assert "MERGE (r:Record" in write_query
    assert "CREATE (r:Record" not in write_query
    assert params["source_url"] == record.source_url
    assert params["dataset"] == "AI26"
    assert params["arena"] == "parliamentary"

    calls_before = len(rag.driver.calls)
    assert rag.rebuild([record]) == 1
    assert "rag_managed = true" in rag.driver.calls[calls_before][0]


def test_record_filters_preserve_canonical_research_metadata():
    record = CanonicalRecord(source_url="https://example.org/1")
    record.source.platform = "bluesky"
    record.source.country = "FI"
    record.source.author = "actor"
    record.content.language = "fi"
    record.source.raw_metadata.update({"collection_id": "AI26", "arena": "grassroots"})
    assert record_filters(record) == {
        "dataset": "AI26",
        "country": "FI",
        "arena": "grassroots",
        "platform": "bluesky",
        "language": "fi",
        "actor": "actor",
        "source": "https://example.org/1",
    }


def test_context_render_is_bounded_and_auditable():
    context = _context(
        [RetrievalItem("id-1", "x" * 100, score=0.5)],
        method="vector",
        filters={},
        embedding_model="embed",
    )
    assert len(context.render(max_chars=40)) <= 40
    assert context.audit.selected_canonical_ids == ["id-1"]


def test_vector_and_embedding_configuration_are_separate():
    settings = Settings(
        rag_enabled=True,
        rag_mode="vector",
        llm_model="gemma4:12b",
        embedding_model="multilingual-embed",
    )
    assert settings.llm_model == "gemma4:12b"
    assert settings.embedding_model == "multilingual-embed"
    assert replace(settings, llm_model="gemma4:26b").embedding_model == "multilingual-embed"
