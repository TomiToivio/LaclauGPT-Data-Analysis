from pathlib import Path

from laclaugpt_data_analysis.discourse_network import DiscourseStatement, EvidenceSpan
from laclaugpt_data_analysis.interoperability.dna import (
    export_dna_project,
    export_dna_statements_csv,
    import_dna_statements,
    import_dna_statements_csv,
    validate_dna_project,
)


def _fixture(text: str = "Äly ja tekoäly 🚀") -> DiscourseStatement:
    quote = "tekoäly"
    start = text.index(quote)
    return DiscourseStatement(
        statement_id="s1",
        source_url="https://example.org/a",
        source_record_id="r1",
        actor_id="actor:1",
        actor_name="Tutkija",
        concept_id="concept:1",
        concept_label="AI regulation",
        concept_type="policy_claim",
        stance="support",
        evidence=EvidenceSpan(quote=quote, start_char=start, end_char=start + len(quote), exact=True),
        coder_type="model",
        coder_id_or_model="synthetic",
        codebook_version="test-v1",
        provenance={"fixture": True},
    )


def test_csv_round_trip_unicode(tmp_path: Path):
    path = tmp_path / "statements.csv"
    export_dna_statements_csv([_fixture()], path)
    rows = import_dna_statements_csv(path)
    assert rows[0].statement_id == "s1"
    assert rows[0].actor_name == "Tutkija"
    assert rows[0].evidence.quote == "tekoäly"


def test_native_dna_round_trip(tmp_path: Path):
    text = "Äly ja tekoäly 🚀"
    path = tmp_path / "project.dna"
    export_dna_project([_fixture(text)], path, document_texts={"https://example.org/a": text})
    assert validate_dna_project(path)["valid"] is True
    rows = import_dna_statements(path, human_coded=True)
    assert len(rows) == 1
    assert rows[0].source_url == "https://example.org/a"
    assert rows[0].actor_name == "Tutkija"
    assert rows[0].evidence.exact is True
    assert rows[0].coder_type == "human"
    assert rows[0].validation_status.value == "validated"
