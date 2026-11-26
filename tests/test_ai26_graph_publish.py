"""Synthetic publisher tests: no model or database connection."""

from __future__ import annotations

import json

from laclaugpt_data_analysis.ai26_graph_publish import build_graph, publish_mongo, write_json
from laclaugpt_data_analysis.interoperability import DiscourseStatement
from laclaugpt_data_analysis.knowledge_graph import SNARelation

SOURCE = "https://example.test/article"
OPTIONS = {"run_id": "synthetic", "codebook_version": "v1", "prompt_version": "p1"}


def inputs():
    statement = DiscourseStatement(
        statement_id="statement:1",
        actor_id="actor-a",
        actor_label="Example A",
        concept_id="concept-a",
        concept_label="Safety",
        qualifier="agree",
        source_url=SOURCE,
        source_document_id="doc-1",
        evidence_id="ev-1",
        provenance_id="prov-1",
        producer={"type": "human", "id": "synthetic"},
    )
    relation = SNARelation(
        relation_id="relation:1",
        source_actor_id="actor-a",
        target_actor_id="actor-b",
        relation_type="mention",
        source_url=SOURCE,
        evidence_ids=["ev-2"],
        provenance_id="prov-2",
    )
    return statement, relation


def test_consumer_wire_contract(tmp_path):
    statement, relation = inputs()
    graph = build_graph([statement], [relation], **OPTIONS)
    output = tmp_path / "graph.json"
    write_json(graph, output)
    data = json.loads(output.read_text())
    assert data["schema_version"] == "1.0.0"
    assert data["project_id"] == "ai26"
    assert data["metadata"]["prompt_version"] == "p1"
    assert {node["id"] for node in data["nodes"]} == {
        "actor-a",
        "actor-b",
        "concept-a",
        "statement:1",
        f"source:{SOURCE}",
    }
    assert {edge["layer"] for edge in data["edges"]} == {"dna", "sna"}
    for edge in data["edges"]:
        assert edge["provenance"]["source_url"] == SOURCE
        assert edge["provenance"]["evidence_ids"]
        assert edge["provenance"]["run_id"] == "synthetic"
        assert edge["provenance"]["codebook_refs"] == ["v1"]
        if edge["layer"] == "dna":
            assert edge["properties"]["qualifier"] == "agree"
            assert edge["properties"]["review_status"] == "PROVISIONAL"
        else:
            assert edge["assertion_kind"] == "empirical"
            assert edge["directed"] is True
    assert output.stat().st_mode & 0o077 == 0


def test_missing_inputs_and_fabricated_ties_are_rejected():
    statement, relation = inputs()
    for statements, relations in (
        ([], []),
        ([statement.model_copy(update={"qualifier": None})], []),
        ([statement.model_copy(update={"review_status": "REJECTED"})], []),
        ([], [relation.model_copy(update={"relation_type": "co-occurrence"})]),
        ([], [relation.model_copy(update={"evidence_ids": []})]),
        ([statement], [relation.model_copy(update={"target_actor_id": statement.concept_id})]),
    ):
        try:
            build_graph(statements, relations, **OPTIONS)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid graph published")


class MemoryCollection:
    def __init__(self):
        self.rows = []

    def create_index(self, *args, **kwargs):
        pass

    def find(self, query, *args):
        return [row for row in self.rows if all(row.get(k) == v for k, v in query.items())]

    def find_one(self, query):
        return next(iter(self.find(query)), None)

    def replace_one(self, query, payload, *, upsert):
        self.rows = [row for row in self.rows if not all(row.get(k) == v for k, v in query.items())]
        self.rows.append(payload)


def test_mongo_initial_publish_and_idempotent_retry():
    statement, relation = inputs()
    graph = build_graph([statement], [relation], **OPTIONS)
    database = {name: MemoryCollection() for name in ("kg_nodes", "kg_edges", "kg_meta")}
    publish_mongo(graph, database)
    publish_mongo(graph, database)
    assert len(database["kg_meta"].rows) == 1
    assert len(database["kg_edges"].rows) == len(graph.edges)
    assert database["kg_meta"].rows[0]["metadata"]["edges"] == len(graph.edges)
    try:
        publish_mongo(build_graph([statement], [], **OPTIONS), database)
    except ValueError:
        pass
    else:
        raise AssertionError("Changed snapshot silently published")
