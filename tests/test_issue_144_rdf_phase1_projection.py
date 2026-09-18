"""Issue #144: RDF is a loss-aware projection of the Phase 1 AI26 canonical schema.

The default Phase 1 pipeline (issue #140) populates more typed fields than the
RDF projection used to materialize. These tests build a synthetic AI26 Phase 1
record, run it through ``materialize_record`` and assert that the supported
Phase 1 analytical objects survive the projection with their evidence,
provenance, review state and uncertainty intact.

They also pin the explicit omissions/typing decisions:

* topics, sentiments, stances and themes ARE projected, but typed as
  ``laclaugpt:DescriptiveObservation`` / ``laclaugpt:Topic`` and marked
  ``laclaugpt:descriptive true`` so polarity cannot be read as affective
  investment;
* the Formula of Populism is projected as its own resource.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

rdflib = pytest.importorskip("rdflib")

from rdflib import Namespace  # noqa: E402

from laclaugpt_data_analysis.canonical import (  # noqa: E402
    CanonicalRecord,
    DiscourseObject,
    Entity,
    Evidence,
    Relation,
    RelationChain,
)
from laclaugpt_data_analysis.models import Topic  # noqa: E402
from laclaugpt_data_analysis.rdf import (  # noqa: E402
    LACLAUGPT,
    materialize_record,
    validate_dataset,
)

NS = Namespace(LACLAUGPT)
PROJECT = "ai26"


def _phase1_record() -> CanonicalRecord:
    """A synthetic record populated the way the Phase 1 pipeline populates one."""
    record = CanonicalRecord(
        source_url="https://example.invalid/ai26/phase1/item-1",
        source={"language": "en", "author": "synthetic"},
        content={"language": "en", "title": "Synthetic AI26 item", "text": "AI and growth."},
    )
    record.evidence.append(
        Evidence(
            evidence_id="ev-1",
            kind="llm_proposed_source_evidence",
            source_url=record.source_url,
            quote="AI and growth.",
            start_offset=0,
            end_offset=14,
        )
    )
    analysis = record.analysis
    analysis.status = "analyzed"
    analysis.summary = "Synthetic summary of the item."
    analysis.uncertainty = ["single document; no corpus comparison"]
    analysis.abstentions = ["no tendentially empty signifier established"]

    # Phase 1 discourse-theoretical objects.
    analysis.discourses = [
        DiscourseObject(object_id="discourse:1", label="accelerationist discourse", kind="discourse",
                        evidence_ids=["ev-1"], confidence=0.4, uncertainty="weak")
    ]
    analysis.imaginaries = [
        DiscourseObject(object_id="imaginary:1", label="AI-driven abundance", kind="imaginary",
                        evidence_ids=["ev-1"], metadata={"corpus_validation_required": True})
    ]
    analysis.us = [DiscourseObject(object_id="us:1", label="the builders", kind="collective_subject", evidence_ids=["ev-1"])]
    analysis.them = [DiscourseObject(object_id="them:1", label="regulators", kind="other", evidence_ids=["ev-1"])]
    analysis.affects = [DiscourseObject(object_id="affect:1", label="hope", kind="affect", uncertainty="weak")]
    analysis.formations = [DiscourseObject(object_id="formation:1", label="accelerationism", kind="formation")]
    analysis.nodal_points = [DiscourseObject(object_id="nodal:1", label="growth", kind="nodal_point")]

    # Chains and relations.
    analysis.equivalence_chains = [
        RelationChain(chain_id="eq:1", chain_type="equivalence", member_refs=["us:1", "imaginary:1"], evidence_ids=["ev-1"])
    ]
    analysis.difference_chains = [
        RelationChain(chain_id="diff:1", chain_type="difference", member_refs=["us:1", "them:1"])
    ]
    analysis.relations = [
        Relation(relation_id="rel:1", relation_type="articulation", source_ref="us:1", target_ref="imaginary:1", evidence_ids=["ev-1"])
    ]
    analysis.antagonisms = [
        Relation(relation_id="ant:1", relation_type="antagonism", source_ref="us:1", target_ref="them:1")
    ]

    # Descriptive computation.
    analysis.topics = [Topic(topic_id="topic:1", canonical_label="AI governance")]
    analysis.sentiments = [DiscourseObject(object_id="sentiment:1", label="positive", kind="sentiment")]
    analysis.stances = [DiscourseObject(object_id="stance:1", label="supportive", kind="stance")]
    analysis.themes = [DiscourseObject(object_id="theme:1", label="growth", kind="theme")]

    # Entities and the Formula of Populism.
    analysis.entities = [Entity(entity_id="entity:1", label="Example Corp", entity_type="organization", evidence_ids=["ev-1"])]
    analysis.formula_of_populism = {
        "populist": True,
        "non_populist_reason": "",
        "us": ["the builders"],
        "frontier": ["regulators"],
    }
    return record


@pytest.fixture(scope="module")
def dataset():
    return materialize_record(_phase1_record(), project_id=PROJECT)


def _subjects_of(dataset, rdf_type):
    return {s for graph in dataset.graphs() for s in graph.subjects(rdflib.RDF.type, rdf_type)}


def test_phase1_discourse_objects_survive_projection(dataset) -> None:
    for rdf_type in (
        NS.Discourse,
        NS.SociotechnicalImaginary,
        NS.CollectiveSubject,
        NS.Other,
        NS.Affect,
        NS.DiscourseFormation,
        NS.NodalPoint,
    ):
        assert _subjects_of(dataset, rdf_type), f"missing Phase 1 class: {rdf_type}"


def test_phase1_objects_retain_provenance_and_review_state(dataset) -> None:
    for rdf_type in (
        NS.Discourse,
        NS.SociotechnicalImaginary,
        NS.CollectiveSubject,
        NS.Other,
        NS.Affect,
    ):
        for node in _subjects_of(dataset, rdf_type):
            assert list(dataset.quads((node, rdflib.PROV.wasGeneratedBy, None))), f"{rdf_type}: no provenance"
            assert list(dataset.quads((node, NS.reviewState, None))), f"{rdf_type}: no review state"


def test_phase1_objects_retain_evidence_and_uncertainty(dataset) -> None:
    discourse = next(iter(_subjects_of(dataset, NS.Discourse)))
    assert list(dataset.quads((discourse, NS.hasEvidence, None))), "discourse lost its evidence link"
    assert list(dataset.quads((discourse, NS.uncertainty, None))), "discourse lost its uncertainty note"
    assert list(dataset.quads((discourse, NS.confidence, None))), "discourse lost its confidence"


def test_corpus_validation_flag_is_preserved(dataset) -> None:
    imaginary = next(iter(_subjects_of(dataset, NS.SociotechnicalImaginary)))
    flags = [str(o) for _, _, o, _ in dataset.quads((imaginary, NS.corpusValidationRequired, None))]
    assert flags == ["true"], "corpus-validation flag must survive projection"


def test_relation_chains_survive_with_members(dataset) -> None:
    equivalence = _subjects_of(dataset, NS.EquivalenceChain)
    difference = _subjects_of(dataset, NS.DifferenceChain)
    assert equivalence and difference
    for chain in equivalence | difference:
        assert list(dataset.quads((chain, rdflib.RDF.type, NS.RelationChain)))
        members = list(dataset.quads((chain, NS.hasMember, None)))
        assert len(members) >= 2, "chain must retain its members"
        assert list(dataset.quads((chain, rdflib.PROV.wasGeneratedBy, None)))
        assert list(dataset.quads((chain, NS.reviewState, None)))


def test_formula_of_populism_is_projected(dataset) -> None:
    formula = _subjects_of(dataset, NS.FormulaOfPopulism)
    assert formula, "Formula of Populism must be projected"
    node = next(iter(formula))
    assert [str(o) for _, _, o, _ in dataset.quads((node, NS.populist, None))] == ["true"]
    assert list(dataset.quads((node, NS.formulaComponent, None))), "formula components must be retained"
    assert list(dataset.quads((node, rdflib.PROV.wasGeneratedBy, None)))


def test_summary_uncertainty_and_abstentions_are_projected(dataset) -> None:
    source = next(iter(_subjects_of(dataset, rdflib.PROV.Entity)))
    assert list(dataset.quads((source, NS.analysisSummary, None))), "analysis summary dropped"
    assert list(dataset.quads((source, NS.uncertainty, None))), "uncertainty dropped"
    assert list(dataset.quads((source, NS.abstention, None))), "abstentions dropped"


def test_descriptive_observations_are_typed_not_theoretical(dataset) -> None:
    """Topics/sentiments/stances/themes must be explicitly descriptive."""
    observations = _subjects_of(dataset, NS.DescriptiveObservation) | _subjects_of(dataset, NS.Topic)
    assert observations, "descriptive observations must be projected"
    for node in observations:
        flagged = [str(o) for _, _, o, _ in dataset.quads((node, NS.descriptive, None))]
        assert flagged == ["true"], f"{node} not marked descriptive"
        # must never be typed as a discourse-theoretical object
        for theoretical in (NS.Affect, NS.DiscursiveFrontier, NS.DiscourseFormation):
            assert not list(dataset.quads((node, rdflib.RDF.type, theoretical))), \
                f"descriptive node {node} typed as {theoretical}"


def test_sentiment_is_not_projected_as_affect(dataset) -> None:
    """Sentiment polarity must not be readable as affective investment."""
    affects = _subjects_of(dataset, NS.Affect)
    sentiments = _subjects_of(dataset, NS.DescriptiveObservation)
    assert affects and sentiments
    assert not (affects & sentiments), "sentiment and affect must be distinct resources"
    # An affect carries the affect label; the sentiment node must not.
    affect_labels = {str(o) for node in affects for _, _, o, _ in dataset.quads((node, rdflib.SKOS.prefLabel, None))}
    sentiment_labels = {str(o) for node in sentiments for _, _, o, _ in dataset.quads((node, rdflib.SKOS.prefLabel, None))}
    assert "hope" in affect_labels
    assert "hope" not in sentiment_labels


def test_phase1_projection_validates(dataset) -> None:
    report = validate_dataset(dataset)
    assert report.conforms, report.text


def test_projection_is_deterministic() -> None:
    """Projection is deterministic in content and in all minted URIs.

    rdflib assigns random blank-node labels at serialization time (e.g. for the
    Web-Annotation selector bnodes), so byte-identical nquads output is not a
    guarantee the library makes. What must be deterministic is the graph itself:
    the same triples, and identical named-URI identities across runs.
    """
    first = materialize_record(_phase1_record(), project_id=PROJECT)
    second = materialize_record(_phase1_record(), project_id=PROJECT)
    assert _canonical_triples(first) == _canonical_triples(second)


def _canonical_triples(dataset):
    """Triples with blank nodes erased, so only real identities are compared."""
    triples = set()
    for graph in dataset.graphs():
        for subject, predicate, obj in graph:
            def clean(term):
                return None if isinstance(term, rdflib.BNode) else str(term)
            triples.add((clean(subject), str(predicate), clean(obj)))
    return triples


def test_shacl_shapes_cover_new_classes() -> None:
    """The SHACL file must declare shapes for the Phase 1 classes (issue #144)."""
    shapes = (REPO / "schemas" / "laclaugpt-rdf.shacl.ttl").read_text(encoding="utf-8")
    for token in (
        "Phase1DiscourseObjectShape",
        "RelationChainShape",
        "FormulaOfPopulismShape",
        "DescriptiveObservationShape",
        "TopicShape",
        "laclaugpt:SociotechnicalImaginary",
        "laclaugpt:CollectiveSubject",
        "laclaugpt:Discourse",
        "laclaugpt:Affect",
    ):
        assert token in shapes, f"SHACL shapes missing: {token}"
