"""End-to-end Phase 1 AI26 semantic/export contract (issue #145).

This synthetic golden record exercises the canonical Phase 1 record, discourse graph
projection, GraphML/GEXF exchange and RDF materialization without calling an LLM.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

rdflib = pytest.importorskip("rdflib")
pytest.importorskip("networkx")

from laclaugpt_data_analysis.canonical import (
    CanonicalRecord,
    DiscourseObject,
    Entity,
    Evidence,
    FrameReference,
    Relation,
    RelationChain,
)
from laclaugpt_data_analysis.canonical_pipeline import build_discourse_graph
from laclaugpt_data_analysis.interoperability import GraphProjection, Producer
from laclaugpt_data_analysis.models import Provenance, Topic
from laclaugpt_data_analysis.portable_exchange import (
    read_gexf,
    read_graphml,
    write_gexf,
    write_graphml,
)
from laclaugpt_data_analysis.rdf import materialize_record, serialize_dataset, validate_dataset


PROJECT = "AI26"
SOURCE = "https://example.invalid/ai26/golden/1"


def _golden_record() -> CanonicalRecord:
    prov = Provenance(
        provenance_id="prov:phase1",
        method="synthetic-phase1-contract",
        model="offline-fixture",
        created_at=datetime(2026, 9, 18, tzinfo=UTC),
        metadata={"stage": "analysis", "project_id": PROJECT},
    )
    record = CanonicalRecord(
        source_url=SOURCE,
        source_native_ids={"document_id": "golden-1"},
        source={"platform": "synthetic", "author": "researcher", "language": "en"},
        content={
            "title": "AI abundance and democratic control",
            "text": (
                "Open AI infrastructure can create shared abundance, but democratic control "
                "must constrain concentrated platform power."
            ),
            "language": "en",
            "frames": [
                FrameReference(
                    id="frame:1",
                    timestamp_seconds=2.5,
                    description="Poster reading OPEN AI FOR ALL",
                    provenance_id="prov:phase1",
                )
            ],
        },
        provenance=[prov],
    )
    record.intermediate.frame_analysis.append(
        {
            "frame_id": "frame:1",
            "analysis": {"visible_text": ["OPEN AI FOR ALL"], "uncertainty": []},
            "model_run": {"offline": True},
        }
    )
    record.evidence.extend(
        [
            Evidence(
                evidence_id="ev:text",
                kind="text_span",
                source_url=SOURCE,
                quote="Open AI infrastructure can create shared abundance",
                start_offset=0,
                end_offset=50,
                provenance_id="prov:phase1",
            ),
            Evidence(
                evidence_id="ev:frame",
                kind="frame",
                source_url=SOURCE,
                ref="frame:1",
                quote="OPEN AI FOR ALL",
                timestamp_seconds=2.5,
                provenance_id="prov:phase1",
            ),
        ]
    )
    a = record.analysis
    a.status = "analyzed"
    a.summary = "A synthetic Phase 1 item articulating openness, abundance and democratic control."
    a.uncertainty = ["single-item fixture; corpus-level validation still required"]
    a.entities = [
        Entity(
            entity_id="entity:platforms",
            label="AI platforms",
            entity_type="organization-class",
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
            review_status="PROVISIONAL",
        )
    ]
    a.topics = [Topic(topic_id="topic:governance", canonical_label="AI governance")]
    a.signifiers = [
        DiscourseObject(
            object_id="signifier:open-ai",
            label="open AI",
            kind="signifier",
            evidence_ids=["ev:text", "ev:frame"],
            provenance_id="prov:phase1",
        )
    ]
    a.nodal_points = [
        DiscourseObject(
            object_id="nodal:abundance",
            label="shared abundance",
            kind="nodal_point",
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
        )
    ]
    a.floating_signifiers = [
        DiscourseObject(
            object_id="floating:control",
            label="control",
            kind="floating_signifier",
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
            metadata={"corpus_validation_required": True},
        )
    ]
    a.empty_signifier_candidates = [
        DiscourseObject(
            object_id="empty:open",
            label="open",
            kind="empty_signifier",
            evidence_ids=["ev:text", "ev:frame"],
            provenance_id="prov:phase1",
            metadata={"corpus_validation_required": True},
        )
    ]
    a.imaginaries = [
        DiscourseObject(
            object_id="imaginary:abundance",
            label="AI-enabled shared abundance",
            kind="imaginary",
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
            metadata={"corpus_validation_required": True},
        )
    ]
    a.affects = [
        DiscourseObject(
            object_id="affect:hope",
            label="hope",
            kind="affect",
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
        )
    ]
    a.frontier = [
        DiscourseObject(
            object_id="frontier:democratic-vs-concentrated",
            label="democratic control / concentrated power",
            kind="frontier",
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
        )
    ]
    a.formations = [
        DiscourseObject(
            object_id="formation:democratic-ai",
            label="democratic AI",
            kind="formation",
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
            metadata={"corpus_validation_required": True},
        )
    ]
    a.relations = [
        Relation(
            relation_id="relation:articulation",
            relation_type="articulation",
            source_ref="signifier:open-ai",
            target_ref="nodal:abundance",
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
        ),
        Relation(
            relation_id="relation:difference",
            relation_type="difference",
            source_ref="frontier:democratic-vs-concentrated",
            target_ref="entity:platforms",
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
        ),
    ]
    a.antagonisms = [
        Relation(
            relation_id="relation:antagonism",
            relation_type="antagonism",
            source_ref="frontier:democratic-vs-concentrated",
            target_ref="entity:platforms",
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
        )
    ]
    a.equivalence_chains = [
        RelationChain(
            chain_id="chain:eq",
            chain_type="equivalence",
            member_refs=["signifier:open-ai", "nodal:abundance"],
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
        )
    ]
    a.difference_chains = [
        RelationChain(
            chain_id="chain:diff",
            chain_type="difference",
            member_refs=["frontier:democratic-vs-concentrated", "entity:platforms"],
            evidence_ids=["ev:text"],
            provenance_id="prov:phase1",
        )
    ]
    record.review.status = "PROVISIONAL"
    record.review.reviewer = "synthetic-researcher"
    record.review.note = "Human review required before substantive interpretation."
    return CanonicalRecord.model_validate(record.canonical_dict())


def _projection(graph: dict) -> GraphProjection:
    return GraphProjection(
        projection_id="phase1-ai26-canonical-discourse",
        graph_type="directed-multigraph",
        node_semantics="Phase 1 canonical discourse objects plus explicit evidence/document nodes",
        edge_semantics="canonical relations plus candidate/evidence topology",
        weighting_method="none",
        projection_method="build_discourse_graph",
        parameters={
            "schema": graph["schema"],
            "lossy_projection": [
                "GraphML/GEXF scalarize nested/list attributes as JSON strings",
                "Canonical record remains authoritative for full typed metadata",
            ],
        },
        source_statement_ids=[],
        producer=Producer(type="tool", id="laclaugpt-data-analysis", version="1"),
        provenance_id="prov:phase1",
    )


def _normalise_graph(graph: dict) -> tuple[set[str], set[tuple[str, str, str]]]:
    node_ids = {str(node["id"]) for node in graph["nodes"]}
    topology = {
        (str(edge["source"]), str(edge["target"]), str(edge["type"]))
        for edge in graph["edges"]
    }
    return node_ids, topology


def test_phase1_ai26_golden_record_survives_graph_and_rdf_exports(tmp_path) -> None:
    record = _golden_record()

    # Canonical validation and Phase 1 scope.
    assert record.schema_version == "1.2.0"
    assert record.content.text
    assert record.content.frames and record.intermediate.frame_analysis
    assert record.review.status == "PROVISIONAL"
    assert record.provenance[0].provenance_id == "prov:phase1"
    assert record.analysis.plugin_results == {}
    assert record.analysis.actor_entity_relations == []
    assert not any(
        token in json.dumps(record.canonical_dict()).lower()
        for token in ("dna_statement", "social_network_analysis", "critical_ai")
    )

    # Canonical discourse graph JSON.
    graph = build_discourse_graph(record)
    node_ids, topology = _normalise_graph(graph)
    for stable_id in (
        SOURCE,
        "ev:text",
        "ev:frame",
        "entity:platforms",
        "signifier:open-ai",
        "nodal:abundance",
        "floating:control",
        "empty:open",
        "imaginary:abundance",
        "affect:hope",
        "frontier:democratic-vs-concentrated",
        "formation:democratic-ai",
    ):
        assert stable_id in node_ids
    assert ("ev:text", "signifier:open-ai", "EVIDENCE_FOR") in topology
    assert ("ev:frame", "signifier:open-ai", "EVIDENCE_FOR") in topology
    assert ("signifier:open-ai", "nodal:abundance", "ARTICULATION") in topology
    assert (
        "frontier:democratic-vs-concentrated",
        "entity:platforms",
        "ANTAGONISM",
    ) in topology

    projection = _projection(graph)
    graphml = tmp_path / "phase1.graphml"
    gexf = tmp_path / "phase1.gexf"
    write_graphml(graphml, nodes=graph["nodes"], edges=graph["edges"], projection=projection)
    write_gexf(gexf, nodes=graph["nodes"], edges=graph["edges"], projection=projection)

    for reader, path in ((read_graphml, graphml), (read_gexf, gexf)):
        nodes, edges, recovered = reader(path)
        assert {str(node["id"]) for node in nodes} == node_ids
        recovered_topology = {
            (str(edge["source"]), str(edge["target"]), str(edge["type"])) for edge in edges
        }
        assert topology <= recovered_topology
        assert recovered.projection_id == projection.projection_id
        assert recovered.parameters["lossy_projection"]

    # RDF is optional in runtime, but when installed it must preserve the Phase 1 semantics.
    dataset = materialize_record(record, project_id=PROJECT)
    report = validate_dataset(dataset)
    assert report.conforms, report.text
    ttl = serialize_dataset(dataset, "turtle")
    assert "SociotechnicalImaginary" in ttl
    assert "DiscourseFormation" in ttl
    assert "NodalPoint" in ttl
    assert "Affect" in ttl
    assert "Articulation" in ttl
    assert "prov:phase1" in ttl or "synthetic-phase1-contract" in ttl
    assert "OPEN AI FOR ALL" in ttl
