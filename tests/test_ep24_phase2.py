from pathlib import Path

from rdflib import Graph

from laclaugpt_data_analysis.ep24_phase2 import (
    ensure_phase2_tables,
    export_phase2,
    persist_statements,
)
from laclaugpt_data_analysis.ep24_roihu import STAGES


def _statements():
    return [
        {
            "statement_id": "s1",
            "record_id": "r1",
            "country": "FI",
            "language": "fi",
            "source_url": "https://example.invalid/1",
            "actor": "Actor A",
            "actor_id": "actor:a",
            "concept": "Concept X",
            "concept_id": "concept:x",
            "stance": "support",
            "evidence_ids": ["r1:e1"],
            "evidence_text": "A supports X",
            "confidence": 0.9,
            "coding_origin": "model",
            "review_state": "unreviewed",
            "prompt_version": "test",
            "phase1_relation": "downstream_of_laclau_analysis",
        },
        {
            "statement_id": "s2",
            "record_id": "r2",
            "country": "PL",
            "language": "pl",
            "source_url": "https://example.invalid/2",
            "actor": "Actor B",
            "actor_id": "actor:b",
            "concept": "Concept X",
            "concept_id": "concept:x",
            "stance": "support",
            "evidence_ids": ["r2:e1"],
            "evidence_text": "B supports X",
            "confidence": 0.8,
            "coding_origin": "model",
            "review_state": "unreviewed",
            "prompt_version": "test",
            "phase1_relation": "downstream_of_laclau_analysis",
        },
        {
            "statement_id": "s3",
            "record_id": "r3",
            "country": "FI",
            "language": "fi",
            "source_url": "",
            "actor": "Actor C",
            "actor_id": "actor:c",
            "concept": "Concept X",
            "concept_id": "concept:x",
            "stance": "reject",
            "evidence_ids": ["r3:e1"],
            "evidence_text": "C rejects X",
            "confidence": 0.8,
            "coding_origin": "model",
            "review_state": "unreviewed",
            "prompt_version": "test",
            "phase1_relation": "downstream_of_laclau_analysis",
        },
    ]


def test_ep24_stage_order_keeps_phase1_before_phase2():
    assert STAGES.index("analysis") < STAGES.index("phase2") < STAGES.index("postprocess")


def test_phase2_exports_are_portable_and_country_scoped(tmp_path: Path):
    db = tmp_path / "data" / "ep24.sqlite3"
    db.parent.mkdir(parents=True)
    ensure_phase2_tables(db)
    for row in _statements():
        persist_statements(db, row["record_id"], [row], "fp", 1.0)

    paths = {
        "root": tmp_path,
        "data": tmp_path / "data",
        "graphs": tmp_path / "graphs",
    }
    outputs = export_phase2(db, paths, fingerprint="run-fp")

    assert Path(outputs["dna_statements_combined"]).exists()
    assert Path(outputs["dna_statements_finland"]).exists()
    assert Path(outputs["dna_statements_poland"]).exists()
    assert Path(outputs["graphml_combined_actor"]).exists()
    assert Path(outputs["gexf_combined_actor"]).exists()
    assert outputs["rdf_validation"] == "passed"

    graph = Graph()
    graph.parse(outputs["rdf"], format="turtle")
    assert len(graph) > 0

    actor_projection = Path(paths["data"] / "dna_actor_projection.csv").read_text()
    assert "congruence" in actor_projection
    assert "conflict" in actor_projection
