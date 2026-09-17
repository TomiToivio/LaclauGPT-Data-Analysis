from __future__ import annotations

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.interoperability import (
    Producer,
    attach_external_result,
    dna_csv_dumps,
    dna_csv_loads,
    export_dats_project,
    export_dna_rows,
    import_dats_project,
    import_dna_rows,
)


def test_dats_round_trip_preserves_unicode_offsets_and_machine_status() -> None:
    payload = {
        "project_id": "synthetic-fi",
        "documents": [
            {
                "id": "doc-1",
                "source_url": "https://example.org/fi/1",
                "text": "Tekoäly muuttaa yhteiskuntaa.",
                "language": "fi",
            }
        ],
        "codes": [
            {"id": "c-root", "label": "AI"},
            {"id": "c-child", "label": "change", "parent_id": "c-root"},
        ],
        "annotations": [
            {
                "id": "ann-1",
                "document_id": "doc-1",
                "code_id": "c-child",
                "start": 0,
                "end": 7,
                "producer_type": "model",
                "producer_id": "synthetic-model",
                "producer_version": "1",
                "confidence": 0.8,
            }
        ],
    }

    project = import_dats_project(payload)
    assert project.documents[0].evidence[0].quote == "Tekoäly"
    assert project.annotations[0].review_status == "PROVISIONAL"

    exported = export_dats_project(project)
    ann = exported["annotations"][0]
    assert ann["start"] == 0
    assert ann["end"] == 7
    assert ann["provisional_ai"] is True
    assert exported["documents"][0]["text"] == payload["documents"][0]["text"]
    assert exported["codes"][1]["parent_id"] == "c-root"


def test_dats_rejects_unreconstructable_span() -> None:
    payload = {
        "project_id": "bad",
        "documents": [{"id": "d", "text": "abc"}],
        "annotations": [
            {"id": "a", "document_id": "d", "code_id": "c", "start": 0, "end": 99}
        ],
    }
    try:
        import_dats_project(payload)
    except ValueError as exc:
        assert "Invalid DATS annotation span" in str(exc)
    else:
        raise AssertionError("unsafe lossy annotation should fail")


def test_dna_statement_round_trip_csv_preserves_semantics() -> None:
    rows = [
        {
            "statement_id": "dna-1",
            "actor_id": "actor-1",
            "actor_label": "Tutkija",
            "concept_id": "concept-1",
            "concept_label": "tekoäly",
            "qualifier": "agreement",
            "source_url": "https://example.org/source",
            "document_id": "doc-1",
            "evidence_id": "ev-1",
            "evidence_text": "tekoäly",
            "timestamp": "2026-09-17T09:00:00+00:00",
            "actor_attributes": '{"country":"FI"}',
            "document_attributes": '{"language":"fi"}',
            "producer_type": "human",
            "producer_id": "coder-1",
            "confidence": "0.9",
            "review_status": "ACCEPTED",
        }
    ]
    statements = import_dna_rows(rows)
    assert statements[0].actor_attributes == {"country": "FI"}
    assert statements[0].concept_label == "tekoäly"

    exported = export_dna_rows(statements)
    assert exported[0]["statement_id"] == "dna-1"
    assert exported[0]["qualifier"] == "agreement"

    csv_text = dna_csv_dumps(statements)
    reloaded = dna_csv_loads(csv_text)
    assert reloaded[0].statement_id == statements[0].statement_id
    assert reloaded[0].review_status == "ACCEPTED"
    assert reloaded[0].timestamp == statements[0].timestamp


def test_external_network_result_stays_descriptive_only() -> None:
    record = CanonicalRecord(source_url="https://example.org/1")
    attach_external_result(
        record,
        namespace="rdna/congruence",
        result={"nodes": 4, "edges": 3},
        producer=Producer(type="tool", id="rDNA", version="x"),
        parameters={"window": "30d"},
        run_id="run-1",
    )
    result = record.analysis.plugin_results["rdna/congruence"]
    assert result["interpretation_status"] == "DESCRIPTIVE_ONLY"
    assert "formation" not in result["result"]
