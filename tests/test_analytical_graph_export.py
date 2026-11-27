"""The AnalyticalGraph producer: coded statements and observed ties become the dashboard's graph.

These tests use invented records. What they pin down is the rule the study depends on: the producer
projects what the pipeline already coded, writes observed replies and explicit handles as SNA ties,
and refuses to turn co-occurrence or a similar label into a relation.
"""

from __future__ import annotations

from typing import Any

from laclaugpt_data_analysis.analytical_graph_export import (
    actor_id,
    build_graph,
    export,
    sna_relations,
    statements_from_result,
)


def _statement(**overrides: Any) -> dict[str, Any]:
    base = {
        "statement_id": "stmt-1",
        "source_url": "urn:example:1",
        "actor_id": "actor:ai-now-institute",
        "actor_name": "AI Now Institute",
        "concept_id": "concept:pacing",
        "concept_label": "pacing",
        "stance": "support",
        "agreement": True,
    }
    base.update(overrides)
    return base


def _document(
    url: str,
    *,
    author: str = "alice",
    text: str = "hello",
    parent: str | None = None,
    statements: list[dict[str, Any]] | None = None,
    created_at: str = "2026-11-20T10:00:00+00:00",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_url": url,
        "source": {
            "author": author,
            "platform": "x",
            "created_at": created_at,
            "parent_source_url": parent,
        },
        "content": {"text": text},
        "analysis": {"plugin_results": {}},
    }
    if statements:
        result["analysis"]["plugin_results"]["dna_statement_coding"] = {
            "proposal": {"statements": statements}
        }
    return {"result": result}


def test_coded_statements_are_read_and_invalidate_rather_than_coerce():
    good = _document("urn:1", statements=[_statement()])
    assert len(statements_from_result(good)) == 1

    broken = _document("urn:2", statements=[{"statement_id": "only-an-id"}])
    assert statements_from_result(broken) == []


def test_a_stored_parent_link_becomes_one_observed_reply_edge():
    documents = [
        _document("urn:parent", author="bob"),
        _document("urn:child", author="alice", parent="urn:parent"),
    ]
    scan = sna_relations(documents)
    assert scan.replies == 1
    relation = scan.relations[0]
    assert relation.relation_type == "reply"
    assert relation.source_actor_id == actor_id("alice")
    assert relation.target_actor_id == actor_id("bob")
    assert relation.source_url == "urn:child"


def test_a_reply_whose_parent_is_outside_the_window_is_not_written():
    scan = sna_relations([_document("urn:child", parent="urn:elsewhere")])
    assert scan.relations == []
    assert scan.unresolved_parents == 1
    assert any("outside the exported window" in note for note in scan.notes)


def test_an_explicit_handle_becomes_a_mention_and_a_bare_name_does_not():
    documents = [
        _document("urn:bob", author="bob"),
        _document("urn:a", author="alice", text="thanks @bob for the paper"),
        _document("urn:b", author="alice", text="bob said the same thing"),
    ]
    scan = sna_relations(documents)
    assert scan.mentions == 1
    mention = next(r for r in scan.relations if r.relation_type == "mention")
    assert mention.target_actor_id == actor_id("bob")
    assert mention.source_url == "urn:a"


def test_a_handle_that_is_not_a_known_author_is_ignored():
    documents = [
        _document("urn:a", author="alice", text="cc @somebodyelse"),
    ]
    assert sna_relations(documents).mentions == 0


def test_the_graph_has_dna_and_sna_layers_and_counts_them():
    documents = [
        _document("urn:parent", author="bob", statements=[_statement(source_url="urn:parent")]),
        _document("urn:child", author="alice", parent="urn:parent", text="@bob agreed"),
    ]
    report = build_graph(documents, include_laclau=False)
    layers = {edge.layer for edge in report.graph.edges}
    assert "dna" in layers, layers
    assert "sna" in layers, layers
    summary = report.summary()
    assert summary["statements"] == 1
    assert summary["sna"]["relations"] >= 1
    assert summary["edges_by_layer"]["dna"] >= 1


def test_an_empty_window_says_so_instead_of_producing_a_graph_that_looks_complete():
    report = build_graph([], include_laclau=False)
    assert report.graph.edges == []
    joined = " ".join(report.notes)
    assert "No coded DNA statements" in joined
    assert "No observed SNA relations" in joined


class _FakeCollection:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._documents = documents

    def find(self, query, projection=None):  # noqa: ANN001 - a tiny stand-in
        return _FakeCursor(self._documents)


class _FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._documents = documents

    def sort(self, *args, **kwargs):
        return self

    def limit(self, count: int):
        self._documents = self._documents[:count]
        return self

    def __iter__(self):
        return iter(self._documents)


class _FakeDatabase:
    """Enough of a pymongo database for the exporter, with no server behind it."""

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._documents = documents
        self.collections: dict[str, Any] = {}
        self.written: list[dict[str, Any]] = []

    def __getitem__(self, name: str):
        self.collections.setdefault(name, _FakeGraphCollection(self))
        if name == "ai26__analysis_results":
            return _FakeCollection(self._documents)
        return self.collections[name]


class _FakeGraphCollection:
    def __init__(self, database: _FakeDatabase) -> None:
        self.database = database
        self.rows: list[dict[str, Any]] = []

    def create_index(self, *args, **kwargs) -> None:
        return None

    def replace_one(self, selector, payload, upsert=False) -> None:  # noqa: ANN001
        self.rows = [
            row for row in self.rows if not all(row.get(k) == v for k, v in selector.items())
        ]
        self.rows.append(payload)
        self.database.written.append(payload)


def test_a_dry_run_never_reaches_the_store():
    database = _FakeDatabase([_document("urn:1", statements=[_statement()])])
    summary = export(database, dry_run=True)
    assert summary["written"] is False
    assert summary["statements"] == 1


def test_a_real_run_upserts_meta_nodes_and_edges():
    database = _FakeDatabase([_document("urn:1", statements=[_statement()])])
    summary = export(database)
    assert summary["written"]["backend"] == "mongodb"
    written = summary["written"]
    assert written["nodes"] > 0
    assert written["edges"] > 0
    assert database.collections["kg_meta"].rows[0]["project_id"] == "ai26"


def test_a_named_run_id_is_recorded_on_metadata_and_every_edge():
    """The graph must name the run that produced it, or it cannot be reproduced (#578)."""
    report = build_graph(
        [_document("urn:run", statements=[_statement(source_url="urn:run")])],
        include_laclau=False,
        run_id="ai26-graph-test-run",
    )
    assert report.graph.metadata["run_id"] == "ai26-graph-test-run"
    assert report.graph.edges, "expected projected edges"
    assert {edge.provenance.run_id for edge in report.graph.edges} == {"ai26-graph-test-run"}
