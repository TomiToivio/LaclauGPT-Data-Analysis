from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.canonical_pipeline import PipelineContext
from laclaugpt_data_analysis.discourse_network import actor_concept_matrix, actor_projection
from laclaugpt_data_analysis.dna_statement_coding import (
    DNAConceptCandidate,
    DNAEntityCandidate,
    DNAStatementBatch,
    DNAStatementCandidate,
    run_optional_dna_statement_coding,
)
from laclaugpt_data_analysis.interoperability.dna import (
    export_dna_project,
    import_dna_statements,
    validate_dna_project,
)
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse


class Provider:
    def __init__(self, batch: DNAStatementBatch):
        self.batch = batch
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content=self.batch.model_dump_json(),
            provenance=LLMCallProvenance(
                requested_mode="local",
                requested_model=request.model,
                resolved_model=request.model,
                actual_mode="local",
                actual_model=request.model,
                endpoint="fake",
            ),
        )


def _record(text: str) -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/dna/cases",
        source_native_ids={"synthetic": "cases-1"},
        raw_capture={"payload": {"synthetic": True}},
        source={
            "platform": "synthetic",
            "created_at": datetime(2026, 9, 17, tzinfo=UTC),
        },
        content={"text": text},
    )


def _context(*, require_binary: bool = False) -> PipelineContext:
    return PipelineContext(
        project_config={
            "analysis": {
                "dna_statement_coding": {
                    "enabled": True,
                    "require_binary_agreement": require_binary,
                }
            }
        }
    )


def _statement(
    *,
    person: str | None,
    organization: str | None,
    concept_id: str,
    concept_label: str,
    quote: str,
    agreement: bool | None,
    status: str,
    provisional: bool = False,
) -> DNAStatementCandidate:
    return DNAStatementCandidate(
        person=DNAEntityCandidate(label=person) if person else None,
        organization=DNAEntityCandidate(label=organization) if organization else None,
        concept=DNAConceptCandidate(
            id=concept_id,
            label=concept_label,
            original_text=quote,
            provisional=provisional,
        ),
        agreement=agreement,
        agreement_status=status,
        evidence_text=quote,
        confidence=0.9,
    )


def test_opposition_projects_to_false_agreement_and_negative_matrix_value() -> None:
    quote = "AI development should not be paused"
    source = f"Ada said {quote}."
    batch = DNAStatementBatch(
        statements=[
            _statement(
                person="Ada",
                organization=None,
                concept_id="pause-ai",
                concept_label="AI development should be paused",
                quote=quote,
                agreement=False,
                status="coded",
            )
        ]
    )
    statements = run_optional_dna_statement_coding(
        _record(source), provider=Provider(batch), context=_context()
    )
    assert statements is not None
    assert statements[0].stance.value == "oppose"
    assert statements[0].metadata["agreement"] is False
    assert actor_concept_matrix(statements)[statements[0].actor_id]["pause-ai"] == -1.0


def test_multiple_claims_and_duplicate_evidence_are_preserved() -> None:
    q1 = "Open models should remain legal"
    q2 = "AI development should be paused"
    source = f"Ada: {q1}. Ada: {q2}. Ada repeated: {q1}."
    first = _statement(
        person="Ada",
        organization=None,
        concept_id="open-legal",
        concept_label="Open models should remain legal",
        quote=q1,
        agreement=True,
        status="coded",
    )
    repeated = first.model_copy(deep=True)
    batch = DNAStatementBatch(
        statements=[
            first,
            _statement(
                person="Ada",
                organization=None,
                concept_id="pause-ai",
                concept_label="AI development should be paused",
                quote=q2,
                agreement=True,
                status="coded",
            ),
            repeated,
        ]
    )
    statements = run_optional_dna_statement_coding(
        _record(source), provider=Provider(batch), context=_context()
    )
    assert statements is not None
    assert len(statements) == 3
    assert statements[0].metadata["duplicate_key"] == statements[2].metadata["duplicate_key"]
    assert statements[0].statement_id != statements[2].statement_id


def test_person_without_supported_organization_keeps_organization_null() -> None:
    quote = "Open models should remain legal"
    batch = DNAStatementBatch(
        statements=[
            _statement(
                person="Ada",
                organization=None,
                concept_id="open-legal",
                concept_label="Open models should remain legal",
                quote=quote,
                agreement=True,
                status="coded",
            )
        ]
    )
    statements = run_optional_dna_statement_coding(
        _record(f"Ada: {quote}."), provider=Provider(batch), context=_context()
    )
    assert statements is not None
    assert statements[0].actor_name == "Ada"
    assert statements[0].metadata["organization"] is None


@pytest.mark.parametrize(
    "source, reason",
    [
        ("Reporter: Ada discussed AI policy.", "reporter narration has no attributable position"),
        ("Ada quoted Bob: 'AI development should be paused.'", "quoted opponent is not endorsed"),
        ("Ada wrote 'sure, pausing AI will fix everything' sarcastically.", "sarcasm makes stance ambiguous"),
    ],
)
def test_uncodable_narration_quotes_and_sarcasm_can_return_only_abstentions(
    source: str, reason: str
) -> None:
    batch = DNAStatementBatch(statements=[], abstentions=[reason])
    record = _record(source)
    statements = run_optional_dna_statement_coding(record, provider=Provider(batch), context=_context())
    assert statements == []
    stage = record.intermediate.stage_outputs["dna_statement_coding"][-1]
    assert stage["proposal"]["abstentions"] == [reason]


def test_require_binary_agreement_excludes_ambiguous_statement() -> None:
    quote = "Perhaps AI development should be paused"
    batch = DNAStatementBatch(
        statements=[
            _statement(
                person="Ada",
                organization=None,
                concept_id="pause-ai",
                concept_label="AI development should be paused",
                quote=quote,
                agreement=None,
                status="ambiguous",
            )
        ]
    )
    statements = run_optional_dna_statement_coding(
        _record(f"Ada: {quote}."),
        provider=Provider(batch),
        context=_context(require_binary=True),
    )
    assert statements == []


def test_codebook_and_provisional_concepts_remain_distinguishable() -> None:
    q1 = "Open models should remain legal"
    q2 = "Public compute should be expanded"
    batch = DNAStatementBatch(
        statements=[
            _statement(
                person="Ada",
                organization=None,
                concept_id="codebook:open-legal",
                concept_label="Open models should remain legal",
                quote=q1,
                agreement=True,
                status="coded",
            ),
            _statement(
                person="Ada",
                organization=None,
                concept_id="provisional:public-compute",
                concept_label="Public compute should be expanded",
                quote=q2,
                agreement=True,
                status="coded",
                provisional=True,
            ),
        ]
    )
    statements = run_optional_dna_statement_coding(
        _record(f"Ada: {q1}. Ada: {q2}."), provider=Provider(batch), context=_context()
    )
    assert statements is not None
    assert statements[0].metadata["concept_provisional"] is False
    assert statements[1].metadata["concept_provisional"] is True


def test_prompt_statement_round_trips_through_native_dna_and_builds_network(tmp_path: Path) -> None:
    quote = "AI development should be paused"
    source = f"Ada: {quote}. Bob: {quote}."
    batch = DNAStatementBatch(
        statements=[
            _statement(
                person="Ada",
                organization=None,
                concept_id="pause-ai",
                concept_label="AI development should be paused",
                quote=quote,
                agreement=True,
                status="coded",
            ),
            _statement(
                person="Bob",
                organization=None,
                concept_id="pause-ai",
                concept_label="AI development should be paused",
                quote=quote,
                agreement=True,
                status="coded",
            ),
        ]
    )
    statements = run_optional_dna_statement_coding(
        _record(source), provider=Provider(batch), context=_context()
    )
    assert statements is not None

    path = tmp_path / "prompt-produced.dna"
    export_dna_project(statements, path, document_texts={"https://example.invalid/dna/cases": source})
    assert validate_dna_project(path)["valid"] is True
    imported = import_dna_statements(path)
    assert len(imported) == 2
    matrix = actor_concept_matrix(imported)
    assert len(matrix) == 2
    projection = actor_projection(imported)
    assert len(projection) == 1
    assert next(iter(projection.values()))["kind"] == "congruence"
