from __future__ import annotations

from laclaugpt_data_analysis.interoperability import DiscourseStatement, Producer
from laclaugpt_data_analysis.portable_exchange import actor_concept_projection


def test_actor_concept_projection_preserves_semantics_without_theory_inference() -> None:
    statements = [
        DiscourseStatement(
            statement_id="s1",
            actor_id="a1",
            actor_label="Actor",
            concept_id="c1",
            concept_label="Concept",
            qualifier="agreement",
            source_url="https://example.org/1",
            source_document_id="d1",
            producer=Producer(type="human", id="coder"),
            review_status="ACCEPTED",
        ),
        DiscourseStatement(
            statement_id="s2",
            actor_id="a1",
            actor_label="Actor",
            concept_id="c1",
            concept_label="Concept",
            qualifier="agreement",
            source_url="https://example.org/2",
            source_document_id="d2",
            producer=Producer(type="human", id="coder"),
            review_status="ACCEPTED",
        ),
    ]
    nodes, edges, projection = actor_concept_projection(statements)
    assert {node["kind"] for node in nodes} == {"actor", "concept"}
    assert edges == [{"source": "a1", "target": "c1", "qualifier": "agreement", "weight": 2}]
    assert projection.projection_method == "actor-concept affiliation"
    assert projection.source_statement_ids == ["s1", "s2"]
    dumped = projection.model_dump(mode="json")
    assert "nodal" not in str(dumped).lower()
    assert "formation" not in str(dumped).lower()
