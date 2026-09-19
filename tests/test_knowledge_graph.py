from __future__ import annotations

from datetime import UTC, datetime

from laclaugpt_data_analysis.canonical import CanonicalRecord, DiscourseObject, Entity, Relation
from laclaugpt_data_analysis.interoperability import DiscourseStatement, Producer
from laclaugpt_data_analysis.knowledge_graph import (
    CSVGraphStore,
    SNADerivedResult,
    SNARelation,
    SQLiteGraphStore,
    canonical_actor_uri,
    merge_graphs,
    project_dna,
    project_laclau_record,
    project_sna,
    serialize_graph_rdf,
)
from laclaugpt_data_analysis.models import Provenance


def laclau_fixture() -> CanonicalRecord:
    record = CanonicalRecord(
        source_url="https://example.org/posts/1",
        source={"platform": "example", "author": "alice", "language": "en"},
        content={"text": "Alice links freedom with openness.", "language": "en"},
    )
    record.provenance.append(
        Provenance(
            provenance_id="prov-laclau",
            method="laclau-discourse-analysis",
            model="gemma4:12b",
            created_at=datetime(2026, 9, 19, tzinfo=UTC),
        )
    )
    record.analysis.codebook_refs.append("codebook:ai26:v1")
    record.analysis.entities.append(
        Entity(
            entity_id="actor:alice",
            label="Alice",
            entity_type="person",
            provenance_id="prov-laclau",
        )
    )
    record.analysis.signifiers.extend(
        [
            DiscourseObject(
                object_id="concept:freedom",
                label="freedom",
                kind="signifier",
                provenance_id="prov-laclau",
            ),
            DiscourseObject(
                object_id="concept:openness",
                label="openness",
                kind="signifier",
                provenance_id="prov-laclau",
            ),
        ]
    )
    record.analysis.relations.append(
        Relation(
            relation_id="rel:freedom-openness",
            relation_type="equivalence",
            source_ref="concept:freedom",
            target_ref="concept:openness",
            provenance_id="prov-laclau",
        )
    )
    return record


def dna_fixture() -> list[DiscourseStatement]:
    return [
        DiscourseStatement(
            statement_id="statement:1",
            actor_id="actor:alice",
            actor_label="Alice",
            concept_id="concept:freedom",
            concept_label="freedom",
            qualifier="agreement",
            source_url="https://example.org/posts/1",
            source_document_id="post-1",
            evidence_id="evidence:1",
            timestamp=datetime(2026, 9, 19, 10, tzinfo=UTC),
            producer=Producer(type="model", id="laclaugpt", version="1"),
            provenance_id="prov-dna",
        )
    ]


def test_laclau_projection_preserves_provenance_and_relation_class():
    graph = project_laclau_record(laclau_fixture(), project_id="AI26", run_id="run-1")
    assert graph.metadata["projection"] == "laclau"
    edge = next(edge for edge in graph.edges if edge.id == "rel:freedom-openness")
    assert edge.assertion_kind == "coded"
    assert edge.provenance.run_id == "run-1"
    assert edge.provenance.codebook_refs == ["codebook:ai26:v1"]
    assert edge.source == "concept:freedom"
    assert edge.target == "concept:openness"


def test_dna_and_sna_reuse_actor_identity_and_keep_temporal_semantics():
    dna = project_dna(dna_fixture(), project_id="AI26", run_id="dna-run")
    sna = project_sna(
        [
            SNARelation(
                relation_id="reply:1",
                source_actor_id="actor:alice",
                target_actor_id="actor:bob",
                relation_type="reply",
                source_url="https://example.org/posts/1",
                timestamp=datetime(2026, 9, 19, 11, tzinfo=UTC),
                platform="example",
            )
        ],
        [
            SNADerivedResult(
                result_id="centrality:alice:day1",
                actor_id="actor:alice",
                metric="centrality",
                value=0.75,
                source_relation_ids=["reply:1"],
                window_start=datetime(2026, 9, 19, tzinfo=UTC),
                window_end=datetime(2026, 9, 20, tzinfo=UTC),
                snapshot_id="2026-09-19",
                method="betweenness-centrality",
            )
        ],
        project_id="AI26",
        run_id="sna-run",
    )
    dna_actor = next(node for node in dna.nodes if node.id == "actor:alice")
    sna_actor = next(node for node in sna.nodes if node.id == "actor:alice")
    assert dna_actor.uri == sna_actor.uri == canonical_actor_uri(
        "https://data.example/laclaugpt", "AI26", "actor:alice"
    )
    derived = next(node for node in sna.nodes if node.id.startswith("derived:"))
    assert derived.assertion_kind == "graph-statistical"
    assert derived.snapshot_id == "2026-09-19"
    assert derived.valid_to is not None


def test_cross_layer_merge_connects_laclau_dna_and_sna():
    merged = merge_graphs(
        project_laclau_record(laclau_fixture(), project_id="AI26"),
        project_dna(dna_fixture(), project_id="AI26"),
        project_sna(
            [
                SNARelation(
                    relation_id="mention:1",
                    source_actor_id="actor:alice",
                    target_actor_id="actor:bob",
                    relation_type="mention",
                    source_url="https://example.org/posts/1",
                )
            ],
            project_id="AI26",
        ),
    )
    assert merged.metadata["projection"] == "cross-layer"
    assert len([node for node in merged.nodes if node.id == "actor:alice"]) == 1
    merged.validate_references()


def test_csv_and_sqlite_round_trip(tmp_path):
    graph = project_dna(dna_fixture(), project_id="AI26")
    csv_store = CSVGraphStore(tmp_path / "csv")
    csv_store.write(graph)
    csv_reloaded = csv_store.read("AI26")
    assert {node.id for node in csv_reloaded.nodes} == {node.id for node in graph.nodes}
    assert {edge.id for edge in csv_reloaded.edges} == {edge.id for edge in graph.edges}

    sqlite_store = SQLiteGraphStore(tmp_path / "kg.sqlite3")
    sqlite_store.write(graph)
    sqlite_reloaded = sqlite_store.read("AI26")
    assert sqlite_reloaded.project_id == graph.project_id
    assert sqlite_reloaded.base_uri == graph.base_uri
    assert {node.id: node.model_dump(mode="json") for node in sqlite_reloaded.nodes} == {
        node.id: node.model_dump(mode="json") for node in graph.nodes
    }
    assert {edge.id: edge.model_dump(mode="json") for edge in sqlite_reloaded.edges} == {
        edge.id: edge.model_dump(mode="json") for edge in graph.edges
    }


def test_common_graph_serializes_to_rdf_jsonld():
    graph = merge_graphs(
        project_laclau_record(laclau_fixture(), project_id="AI26", run_id="laclau-run"),
        project_dna(dna_fixture(), project_id="AI26", run_id="dna-run"),
    )
    jsonld = serialize_graph_rdf(graph, "json-ld")
    assert "GraphRelation" in jsonld
    assert "assertionKind" in jsonld
    assert "wasGeneratedBy" in jsonld
    assert "actor%3Aalice" in jsonld or "actor%253Aalice" in jsonld
