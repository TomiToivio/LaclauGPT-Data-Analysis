from __future__ import annotations

from pathlib import Path

from pyshacl import validate

from laclaugpt_data_analysis.canonical import CanonicalRecord, DiscourseObject, Relation
from laclaugpt_data_analysis.knowledge_graph import graph_to_rdf, project_laclau_record


def test_knowledge_graph_rdf_conforms_to_shacl():
    record = CanonicalRecord(
        source_url="https://example.org/source/1",
        content={"text": "AI links speed and progress."},
    )
    record.analysis.signifiers.extend(
        [
            DiscourseObject(object_id="speed", label="speed", kind="signifier"),
            DiscourseObject(object_id="progress", label="progress", kind="signifier"),
        ]
    )
    record.analysis.relations.append(
        Relation(
            relation_id="r1",
            relation_type="equivalence",
            source_ref="speed",
            target_ref="progress",
        )
    )
    dataset = graph_to_rdf(project_laclau_record(record, project_id="AI26"))
    shapes = Path(__file__).parents[1] / "schemas" / "knowledge-graph.shacl.ttl"
    conforms, _, report = validate(
        data_graph=dataset,
        shacl_graph=str(shapes),
        inference="rdfs",
        abort_on_first=False,
    )
    assert conforms, str(report)
