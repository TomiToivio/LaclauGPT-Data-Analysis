from __future__ import annotations

import json
from datetime import UTC, datetime

from laclaugpt_data_analysis.canonical import (
    CanonicalRecord,
    DiscourseObject,
    Entity,
    Evidence,
    Relation,
    RelationChain,
)
from laclaugpt_data_analysis.canonical_pipeline import build_discourse_graph
from laclaugpt_data_analysis.interoperability import GraphProjection
from laclaugpt_data_analysis.models import Provenance, Topic
from laclaugpt_data_analysis.portable_exchange import (
    read_gexf,
    read_graphml,
    write_gexf,
    write_graphml,
)
from laclaugpt_data_analysis.rdf import import_profile_dataset, materialize_record, validate_dataset


def golden_record() -> CanonicalRecord:
    text = (
        "AI should serve democratic society. Safety and innovation must be balanced. "
        "Public institutions should govern advanced AI instead of unaccountable firms."
    )
    source_url = "https://example.test/ai26/golden-record"
    prov = Provenance(
        provenance_id="prov:phase1-golden",
        method="synthetic-offline-contract",
        pipeline_version="ai26-phase1-legacy-order-v1",
        created_at=datetime(2026, 9, 18, 9, 0, tzinfo=UTC),
        metadata={"issue": 145, "synthetic": True},
    )
    evidence = [
        Evidence(
            evidence_id="ev:text:democracy",
            kind="text-span",
            source_url=source_url,
            quote="AI should serve democratic society.",
            start_offset=0,
            end_offset=35,
            provenance_id=prov.provenance_id,
            metadata={"exact": True},
        ),
        Evidence(
            evidence_id="ev:text:balance",
            kind="text-span",
            source_url=source_url,
            quote="Safety and innovation must be balanced.",
            start_offset=36,
            end_offset=75,
            provenance_id=prov.provenance_id,
            metadata={"exact": True},
        ),
        Evidence(
            evidence_id="ev:frame:1",
            kind="frame",
            source_url=source_url,
            ref="frame-1",
            timestamp_seconds=1.5,
            provenance_id=prov.provenance_id,
            metadata={"description": "Public hearing scene with AI policy slogan"},
        ),
    ]

    record = CanonicalRecord(
        source_url=source_url,
        source_native_ids={"synthetic_id": "ai26-phase1-golden"},
        source={
            "platform": "synthetic",
            "source_type": "multimodal-post",
            "author": "AI26 contract fixture",
            "language": "en",
            "created_at": datetime(2026, 9, 18, 8, 30, tzinfo=UTC),
            "collection_method": "offline-synthetic",
        },
        content={
            "title": "AI26 Phase 1 golden record",
            "text": text,
            "language": "en",
            "frames": [
                {
                    "id": "frame-1",
                    "timestamp_seconds": 1.5,
                    "description": "Public hearing scene with AI policy slogan",
                    "provenance_id": prov.provenance_id,
                }
            ],
        },
        intermediate={
            "frame_analysis": [
                {
                    "frame_id": "frame-1",
                    "timestamp_seconds": 1.5,
                    "analysis": {
                        "scene_and_participants": ["public hearing", "speaker"],
                        "visible_text": ["Democratic AI"],
                        "semiotic_contribution": "Frames democratic governance as legitimate AI control.",
                    },
                }
            ]
        },
        evidence=evidence,
        provenance=[prov],
        review={
            "status": "PROVISIONAL",
            "reviewer": "synthetic-human-review",
            "reviewed_at": datetime(2026, 9, 18, 9, 5, tzinfo=UTC),
            "note": "Synthetic evidence-grounded Phase 1 contract fixture.",
            "flags": ["offline-test-only"],
        },
    )

    record.analysis.entities = [
        Entity(
            entity_id="entity:public-institutions",
            label="public institutions",
            entity_type="organization",
            evidence_ids=["ev:text:democracy"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        )
    ]
    record.analysis.topics = [
        Topic(
            topic_id="topic:ai-governance",
            canonical_label="AI governance",
            metadata={"source_stage": "summary", "review_status": "PROVISIONAL"},
        )
    ]
    record.analysis.signifiers = [
        DiscourseObject(
            object_id="signifier:safety",
            label="safety",
            kind="signifier",
            evidence_ids=["ev:text:balance"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        )
    ]
    record.analysis.nodal_points = [
        DiscourseObject(
            object_id="nodal:democratic-ai",
            label="democratic AI",
            kind="nodal_point",
            evidence_ids=["ev:text:democracy", "ev:frame:1"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        )
    ]
    record.analysis.floating_signifiers = [
        DiscourseObject(
            object_id="floating:innovation",
            label="innovation",
            kind="floating_signifier",
            evidence_ids=["ev:text:balance"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
            metadata={"corpus_validation_required": True},
        )
    ]
    record.analysis.empty_signifier_candidates = [
        DiscourseObject(
            object_id="empty:democracy",
            label="democracy",
            kind="empty_signifier",
            evidence_ids=["ev:text:democracy"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
            metadata={"corpus_validation_required": True},
        )
    ]
    record.analysis.formations = [
        DiscourseObject(
            object_id="formation:democratic-ai",
            label="democratic AI governance",
            kind="formation",
            evidence_ids=["ev:text:democracy", "ev:text:balance"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
            metadata={"corpus_validation_required": True},
        )
    ]
    record.analysis.imaginaries = [
        DiscourseObject(
            object_id="imaginary:public-ai",
            label="publicly governed advanced AI",
            kind="imaginary",
            evidence_ids=["ev:text:democracy", "ev:frame:1"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        )
    ]
    record.analysis.frontier = [
        DiscourseObject(
            object_id="frontier:public-vs-unaccountable",
            label="public institutions / unaccountable firms",
            kind="frontier",
            evidence_ids=["ev:text:democracy"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        )
    ]
    record.analysis.affects = [
        DiscourseObject(
            object_id="affect:concern",
            label="concern about unaccountable control",
            kind="affect",
            evidence_ids=["ev:text:democracy"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        )
    ]

    record.analysis.relations = [
        Relation(
            relation_id="relation:articulation:1",
            relation_type="ARTICULATES",
            source_ref="nodal:democratic-ai",
            target_ref="signifier:safety",
            evidence_ids=["ev:text:balance"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        ),
        Relation(
            relation_id="relation:equivalence:1",
            relation_type="EQUIVALENT_TO",
            source_ref="nodal:democratic-ai",
            target_ref="empty:democracy",
            evidence_ids=["ev:text:democracy"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        ),
        Relation(
            relation_id="relation:difference:1",
            relation_type="DIFFERENTIATED_FROM",
            source_ref="nodal:democratic-ai",
            target_ref="floating:innovation",
            evidence_ids=["ev:text:balance"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        ),
    ]
    record.analysis.equivalence_chains = [
        RelationChain(
            chain_id="equivalence_chain:1",
            chain_type="equivalence",
            member_refs=["nodal:democratic-ai", "empty:democracy"],
            evidence_ids=["ev:text:democracy"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        )
    ]
    record.analysis.difference_chains = [
        RelationChain(
            chain_id="difference_chain:1",
            chain_type="difference",
            member_refs=["nodal:democratic-ai", "floating:innovation"],
            evidence_ids=["ev:text:balance"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        )
    ]
    record.analysis.antagonisms = [
        Relation(
            relation_id="antagonism:1",
            relation_type="ANTAGONISTIC_TO",
            source_ref="frontier:public-vs-unaccountable",
            target_ref="formation:democratic-ai",
            evidence_ids=["ev:text:democracy"],
            provenance_id=prov.provenance_id,
            review_status="PROVISIONAL",
        )
    ]
    record.analysis.status = "analyzed"
    return record


def phase1_projection(record: CanonicalRecord):
    graph = build_discourse_graph(record)
    evidence_by_id = {item.evidence_id: item for item in record.evidence}
    node_by_id = {node["id"]: node for node in graph["nodes"]}

    for obj in (
        record.analysis.signifiers
        + record.analysis.formations
        + record.analysis.imaginaries
        + record.analysis.nodal_points
    ):
        node = node_by_id[obj.object_id]
        node["evidence_ids"] = list(obj.evidence_ids)
        node["provenance_id"] = obj.provenance_id
        node["evidence_kinds"] = [
            evidence_by_id[evidence_id].kind for evidence_id in obj.evidence_ids
        ]

    relation_edges = [
        {
            "source": relation.source_ref,
            "target": relation.target_ref,
            "type": relation.relation_type,
            "relation_id": relation.relation_id,
            "evidence_ids": list(relation.evidence_ids),
            "provenance_id": relation.provenance_id,
        }
        for relation in record.analysis.relations + record.analysis.antagonisms
    ]
    graph["edges"].extend(relation_edges)

    projection = GraphProjection(
        projection_id="ai26-phase1-discourse-golden",
        graph_type="directed-multigraph",
        node_semantics="Phase 1 canonical discourse objects plus source document",
        edge_semantics="candidate membership and explicit evidence-grounded discourse relations",
        weighting_method="unweighted",
        projection_method="canonical discourse graph plus explicit relation edges",
        parameters={
            "lossy": True,
            "omits": [
                "full canonical record fields",
                "review notes and corrections",
                "topic/entity fields not represented as graph nodes",
                "relation-chain ordering beyond explicit relation edges",
                "frame-analysis payloads beyond evidence references",
            ],
        },
        producer={"type": "tool", "id": "laclaugpt-data-analysis", "version": "1"},
        provenance_id="prov:phase1-golden",
    )
    return graph, projection


def _stable_topology(nodes, edges):
    node_ids = {node["id"] for node in nodes}
    relation_edges = {
        (
            edge["source"],
            edge["target"],
            edge.get("relation_id", ""),
            edge.get("type", ""),
            edge.get("evidence_ids", ""),
        )
        for edge in edges
        if edge.get("relation_id")
    }
    return node_ids, relation_edges


def test_phase1_ai26_golden_record_cross_representation_contract(tmp_path):
    record = golden_record()
    payload = record.canonical_dict()
    validated = CanonicalRecord.model_validate(payload)

    assert validated.source_url == record.source_url
    assert {item.kind for item in validated.analysis.signifiers} == {
        "signifier",
    }
    assert validated.content.frames[0].id == "frame-1"
    assert {item.kind for item in validated.evidence} == {"text-span", "frame"}

    graph, projection = phase1_projection(validated)
    graph_json = json.loads(json.dumps(graph, sort_keys=True))
    assert graph_json["schema"] == "laclaugpt-discourse-graph-v1"
    assert "nodal:democratic-ai" in {node["id"] for node in graph_json["nodes"]}
    assert any(
        edge.get("relation_id") == "relation:articulation:1"
        and edge["evidence_ids"] == ["ev:text:balance"]
        for edge in graph_json["edges"]
    )
    assert any(
        node["id"] == "nodal:democratic-ai"
        and node["evidence_ids"] == ["ev:text:democracy", "ev:frame:1"]
        for node in graph_json["nodes"]
    )

    graphml_path = tmp_path / "phase1.graphml"
    gexf_path = tmp_path / "phase1.gexf"
    write_graphml(
        graphml_path,
        nodes=graph_json["nodes"],
        edges=graph_json["edges"],
        projection=projection,
    )
    write_gexf(
        gexf_path,
        nodes=graph_json["nodes"],
        edges=graph_json["edges"],
        projection=projection,
    )

    graphml_nodes, graphml_edges, graphml_projection = read_graphml(graphml_path)
    gexf_nodes, gexf_edges, gexf_projection = read_gexf(gexf_path)
    expected_topology = _stable_topology(graph_json["nodes"], graph_json["edges"])
    assert _stable_topology(graphml_nodes, graphml_edges) == expected_topology
    assert _stable_topology(gexf_nodes, gexf_edges) == expected_topology
    assert graphml_projection.projection_id == projection.projection_id
    assert gexf_projection.parameters["lossy"] is True

    dataset = materialize_record(validated, project_id="AI26", run_id="phase1-golden")
    report = validate_dataset(dataset)
    assert report.conforms is True
    imported = import_profile_dataset(dataset)
    articulation = next(item for item in imported if item.get("id") == "relation:articulation:1")
    assert articulation["review_state"] == "PROVISIONAL"
    assert articulation["generated_by"]
    assert articulation["evidence"]

    phase2_keys = {"dna_statement_coding", "sna", "critical_ai", "ant", "valueflows"}
    canonical_json = json.dumps(validated.canonical_dict(), sort_keys=True).lower()
    for key in phase2_keys:
        assert key not in validated.analysis.plugin_results
        assert key not in validated.analysis.plugin_failures
    assert '"discourse_statement"' not in canonical_json
    assert '"critical_ai"' not in canonical_json

    assert projection.parameters["lossy"] is True
    assert "review notes and corrections" in projection.parameters["omits"]
