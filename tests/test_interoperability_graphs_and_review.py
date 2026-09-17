from __future__ import annotations

from laclaugpt_data_analysis.dats_review import (
    import_dats_human_correction,
    provisional_ai_annotation,
)
from laclaugpt_data_analysis.graph_exchange import statements_to_actor_concept_graph
from laclaugpt_data_analysis.interoperability import (
    GraphProjection,
    Producer,
    import_dna_rows,
)


def test_provisional_ai_annotation_cannot_default_to_human_verified() -> None:
    ann = provisional_ai_annotation(
        annotation_id="a1",
        source_url="https://example.org/1",
        evidence_id="e1",
        code_id="c1",
        model_id="model-x",
        model_version="1",
        confidence=0.7,
        prompt_id="prompt-1",
        run_id="run-1",
    )
    assert ann.producer.type == "model"
    assert ann.review_status == "PROVISIONAL"
    assert ann.metadata["human_verified"] is False


def test_dats_human_correction_is_explicit_review_event() -> None:
    review = import_dats_human_correction(
        {
            "id": "review-7",
            "target_id": "annotation-4",
            "reviewer": "researcher-1",
            "decision": "REVISED",
            "reviewed_at": "2026-09-17T09:30:00Z",
            "corrections": {"code_id": "c2"},
        }
    )
    assert review.decision == "REVISED"
    assert review.corrections == {"code_id": "c2"}
    assert review.external_ids[0].system == "dats"


def test_actor_concept_graph_carries_projection_semantics() -> None:
    statements = import_dna_rows(
        [
            {
                "statement_id": "s1",
                "actor_id": "a1",
                "actor_label": "Actor",
                "concept_id": "c1",
                "concept_label": "Concept",
                "qualifier": "agreement",
                "source_url": "https://example.org/1",
                "producer_type": "human",
                "producer_id": "coder",
            }
        ]
    )
    projection = GraphProjection(
        projection_id="p1",
        graph_type="actor-concept-bipartite",
        node_semantics="actors and coded concepts",
        edge_semantics="coded actor-concept statement occurrence",
        weighting_method="statement count",
        projection_method="bipartite",
        source_statement_ids=["dna:s1"],
        producer=Producer(type="tool", id="laclaugpt-data-analysis"),
    )
    graph = statements_to_actor_concept_graph(statements, projection)
    assert graph.graph["interpretation_status"] == "DESCRIPTIVE_ONLY"
    assert graph.graph["edge_semantics"] == "coded actor-concept statement occurrence"
    assert graph["actor:a1"]["concept:c1"]["weight"] == 1.0
