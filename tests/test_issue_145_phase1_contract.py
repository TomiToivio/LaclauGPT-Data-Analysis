from __future__ import annotations

import json
from datetime import UTC, datetime

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
from laclaugpt_data_analysis.rdf import (
    import_profile_dataset,
    materialize_record,
    serialize_dataset,
    validate_dataset,
)


def golden_ai26_record() -> CanonicalRecord:
    source_url = "https://example.invalid/ai26/golden-145"
    record = CanonicalRecord(
        source_url=source_url,
        source_native_ids={"synthetic": "ai26-golden-145"},
        source={
            "platform": "synthetic",
            "author": "AI26 Research Fixture",
            "language": "en",
            "created_at": datetime(2026, 9, 18, 8, 0, tzinfo=UTC),
        },
        content={
            "title": "Democratic AI future",
            "text": (
                "Citizens demand democratic control of AI. Open systems should serve the public, "
                "not closed monopolies. Freedom and openness belong together."
            ),
            "frames": [
                FrameReference(
                    id="frame-1",
                    timestamp_seconds=1.5,
                    description="A protest placard reads: Democratic AI for everyone.",
                    provenance_id="prov-1",
                ).model_dump(mode="json")
            ],
        },
    )
    record.provenance.append(
        Provenance(
            provenance_id="prov-1",
            method="synthetic-phase1-contract",
            model="offline-fixture",
            created_at=datetime(2026, 9, 18, 8, 5, tzinfo=UTC),
            metadata={"project": "AI26", "phase": "1"},
        )
    )
    record.evidence.extend(
        [
            Evidence(
                evidence_id="ev-text",
                kind="text_span",
                source_url=source_url,
                quote="Citizens demand democratic control of AI.",
                start_offset=0,
                end_offset=41,
                provenance_id="prov-1",
            ),
            Evidence(
                evidence_id="ev-frame",
                kind="frame",
                source_url=source_url,
                ref="frame-1",
                quote="Democratic AI for everyone.",
                timestamp_seconds=1.5,
                provenance_id="prov-1",
            ),
        ]
    )
    record.analysis.entities.append(
        Entity(
            entity_id="entity-citizens",
            label="Citizens",
            entity_type="collective",
            evidence_ids=["ev-text"],
            provenance_id="prov-1",
        )
    )
    record.analysis.topics.append(
        Topic(
            topic_id="topic-ai-governance",
            canonical_label="AI governance",
            aliases=["democratic AI"],
            description="Synthetic Phase 1 topic candidate.",
        )
    )
    record.analysis.signifiers.extend(
        [
            DiscourseObject(
                object_id="signifier-ai",
                label="AI",
                kind="signifier",
                evidence_ids=["ev-text", "ev-frame"],
                confidence=0.95,
                provenance_id="prov-1",
            ),
            DiscourseObject(
                object_id="signifier-freedom",
                label="freedom",
                kind="signifier",
                evidence_ids=["ev-text"],
                confidence=0.85,
                provenance_id="prov-1",
            ),
            DiscourseObject(
                object_id="signifier-openness",
                label="openness",
                kind="signifier",
                evidence_ids=["ev-text"],
                confidence=0.84,
                provenance_id="prov-1",
            ),
        ]
    )
    record.analysis.nodal_points.append(
        DiscourseObject(
            object_id="nodal-democratic-ai",
            label="democratic AI",
            kind="nodal_point_candidate",
            evidence_ids=["ev-text", "ev-frame"],
            confidence=0.75,
            provenance_id="prov-1",
            metadata={"corpus_validation_required": True},
        )
    )
    record.analysis.floating_signifiers.append(
        DiscourseObject(
            object_id="floating-freedom",
            label="freedom",
            kind="floating_signifier_candidate",
            evidence_ids=["ev-text"],
            confidence=0.6,
            provenance_id="prov-1",
            metadata={"corpus_validation_required": True},
        )
    )
    record.analysis.empty_signifier_candidates.append(
        DiscourseObject(
            object_id="empty-democracy",
            label="democracy",
            kind="empty_signifier_candidate",
            evidence_ids=["ev-text", "ev-frame"],
            confidence=0.5,
            provenance_id="prov-1",
            metadata={"corpus_validation_required": True},
        )
    )
    record.analysis.formations.append(
        DiscourseObject(
            object_id="formation-democratic-ai",
            label="democratic AI formation",
            kind="formation_candidate",
            evidence_ids=["ev-text", "ev-frame"],
            confidence=0.55,
            provenance_id="prov-1",
            metadata={"corpus_validation_required": True},
        )
    )
    record.analysis.imaginaries.append(
        DiscourseObject(
            object_id="imaginary-public-ai",
            label="AI as democratic public infrastructure",
            kind="sociotechnical_imaginary_candidate",
            evidence_ids=["ev-text", "ev-frame"],
            confidence=0.65,
            provenance_id="prov-1",
        )
    )
    record.analysis.frontier.append(
        DiscourseObject(
            object_id="frontier-public-monopoly",
            label="public control / closed monopoly",
            kind="frontier_candidate",
            evidence_ids=["ev-text"],
            confidence=0.7,
            provenance_id="prov-1",
        )
    )
    record.analysis.affects.append(
        DiscourseObject(
            object_id="affect-hope",
            label="hopeful democratic investment",
            kind="affect",
            evidence_ids=["ev-frame"],
            confidence=0.6,
            provenance_id="prov-1",
        )
    )
    record.analysis.relations.extend(
        [
            Relation(
                relation_id="rel-articulation",
                relation_type="ARTICULATES",
                source_ref="signifier-freedom",
                target_ref="signifier-openness",
                evidence_ids=["ev-text"],
                provenance_id="prov-1",
            ),
            Relation(
                relation_id="rel-antagonism",
                relation_type="ANTAGONISTIC_TO",
                source_ref="nodal-democratic-ai",
                target_ref="frontier-public-monopoly",
                evidence_ids=["ev-text"],
                provenance_id="prov-1",
            ),
        ]
    )
    record.analysis.equivalence_chains.append(
        RelationChain(
            chain_id="eq-democratic-values",
            chain_type="equivalence",
            member_refs=["signifier-freedom", "signifier-openness"],
            evidence_ids=["ev-text"],
            provenance_id="prov-1",
        )
    )
    record.analysis.difference_chains.append(
        RelationChain(
            chain_id="diff-public-monopoly",
            chain_type="difference",
            member_refs=["nodal-democratic-ai", "frontier-public-monopoly"],
            evidence_ids=["ev-text"],
            provenance_id="prov-1",
        )
    )
    record.review.status = "PROVISIONAL"
    record.review.reviewer = "synthetic-researcher"
    record.review.note = "Offline golden record for Phase 1 contract verification."
    return record


def projection_for() -> GraphProjection:
    return GraphProjection(
        projection_id="ai26-phase1-canonical-discourse",
        graph_type="directed-multigraph",
        node_semantics="canonical Phase 1 documents, evidence and discourse objects",
        edge_semantics="candidate membership, evidence support and explicit discourse relations",
        weighting_method="none",
        projection_method="canonical discourse graph projection",
        parameters={
            "lossy": [
                "nested metadata is JSON-stringified in GraphML/GEXF",
                "canonical ordering is not semantically significant in graph formats",
                "RDF omits raw/private source payloads and some non-profile canonical fields",
            ]
        },
        producer=Producer(type="tool", id="laclaugpt-data-analysis", version="1"),
        provenance_id="prov-1",
    )


def _assert_phase1_only(record: CanonicalRecord) -> None:
    dump = json.dumps(record.canonical_dict(), ensure_ascii=False, sort_keys=True).casefold()
    for forbidden in ("dna_statement", "critical_ai", "network_centrality", "brokerage"):
        assert forbidden not in dump


def test_phase1_ai26_golden_record_survives_graph_exchange_and_rdf(tmp_path) -> None:
    record = golden_ai26_record()
    validated = CanonicalRecord.model_validate(record.canonical_dict())
    assert validated.content.frames[0].id == "frame-1"
    assert validated.review.status == "PROVISIONAL"
    _assert_phase1_only(validated)

    graph = build_discourse_graph(validated)
    node_ids = {node["id"] for node in graph["nodes"]}
    edge_ids = {edge.get("id") for edge in graph["edges"]}
    assert {"ev-text", "ev-frame", "signifier-ai", "nodal-democratic-ai"} <= node_ids
    assert {"rel-articulation", "rel-antagonism"} <= edge_ids
    assert any(edge["type"] == "EVIDENCE_FOR" and edge["source"] == "ev-text" for edge in graph["edges"])
    assert any(edge["type"] == "EQUIVALENT_TO" for edge in graph["edges"])
    assert any(edge["type"] == "DIFFERENTIATED_FROM" for edge in graph["edges"])

    graph_round_trip = json.loads(json.dumps(graph, ensure_ascii=False, sort_keys=True))
    assert graph_round_trip["source_url"] == validated.source_url
    assert {node["id"] for node in graph_round_trip["nodes"]} == node_ids

    projection = projection_for()
    graphml_path = tmp_path / "ai26-phase1.graphml"
    gexf_path = tmp_path / "ai26-phase1.gexf"
    write_graphml(graphml_path, nodes=graph["nodes"], edges=graph["edges"], projection=projection)
    write_gexf(gexf_path, nodes=graph["nodes"], edges=graph["edges"], projection=projection)

    graphml_nodes, graphml_edges, graphml_projection = read_graphml(graphml_path)
    gexf_nodes, gexf_edges, gexf_projection = read_gexf(gexf_path)
    assert {node["id"] for node in graphml_nodes} == node_ids
    assert {node["id"] for node in gexf_nodes} == node_ids
    assert graphml_projection.projection_id == projection.projection_id
    assert gexf_projection.projection_id == projection.projection_id
    assert any(edge.get("type") == "EVIDENCE_FOR" for edge in graphml_edges)
    assert any(edge.get("type") == "EVIDENCE_FOR" for edge in gexf_edges)
    assert any(edge.get("laclaugpt_edge_id") == "rel-articulation" for edge in graphml_edges)
    assert any(edge.get("id") == "rel-articulation" for edge in gexf_edges)

    dataset = materialize_record(validated, project_id="AI26")
    report = validate_dataset(dataset)
    assert report.conforms is True
    imported = import_profile_dataset(dataset)
    assert any(item["kind"] == "source" and item["source_url"] == validated.source_url for item in imported)
    assert any(item["kind"] == "articulation" and item["id"] == "rel-articulation" for item in imported)
    nquads = serialize_dataset(dataset, "nquads")
    assert "ev-text" in nquads
    assert "rel-articulation" in nquads
    assert "https://w3id.org/laclaugpt/Articulation" in nquads
