"""Evidence-only, explicitly authorized Phase 2 steps."""

import pytest

from pipeline_models import DNAResult, HumanPipelineRecord, LaclauResult
from step_06_dna import analyze_dna
from step_07_sna import analyze_sna

SOURCE = "https://example.test/article"


def record(**metadata):
    return HumanPipelineRecord(
        source_url=SOURCE,
        project="ai26",
        source_text="A supports safety.",
        metadata=metadata,
    )


def statement(**overrides):
    return {
        "statement_id": "statement:1",
        "actor_id": "actor:a",
        "actor_label": "A",
        "concept_id": "concept:safety",
        "concept_label": "Safety",
        "qualifier": "agree",
        "source_url": SOURCE,
        "source_document_id": "doc-1",
        "evidence_id": "ev-1",
        "provenance_id": "prov-1",
        "producer": {"type": "human", "id": "test"},
        **overrides,
    }


def relation(**overrides):
    return {
        "relation_id": "relation:1",
        "source_actor_id": "actor:a",
        "target_actor_id": "actor:b",
        "relation_type": "mention",
        "source_url": SOURCE,
        "evidence_ids": ["ev-2"],
        "provenance_id": "prov-2",
        **overrides,
    }


def test_explicit_network_steps():
    source = record(dna_statements=[statement()], sna_relations=[relation()])
    dna = analyze_dna(source, LaclauResult(analysis="synthetic"))
    sna = analyze_sna(source, dna)
    assert len(dna.claims) == 1
    assert len(dna.edges) == 3
    assert len(sna.edges) == 1
    assert sna.edges[0]["provenance"]["evidence_ids"] == ["ev-2"]
    assert sna.edges[0]["directed"] is True


def test_abstention_does_not_infer_networks():
    source = record(dna_statements=[statement(qualifier=None)])
    dna = analyze_dna(source, LaclauResult(analysis="A and B", demands=["safety"]))
    assert not dna.claims
    assert not dna.edges
    assert not analyze_sna(source, dna).edges


@pytest.mark.parametrize(
    "bad",
    [
        {"source_url": "https://example.test/other"},
        {"relation_type": "co-occurrence"},
        {"evidence_ids": []},
    ],
)
def test_sna_rejects_invalid_ties(bad):
    with pytest.raises(ValueError):
        analyze_sna(record(sna_relations=[relation(**bad)]), DNAResult())


def test_dna_rejects_cross_source():
    with pytest.raises(ValueError):
        analyze_dna(
            record(dna_statements=[statement(source_url="https://example.test/other")]),
            LaclauResult(analysis="synthetic"),
        )
