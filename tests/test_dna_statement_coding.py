from __future__ import annotations

from datetime import UTC, datetime

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.canonical_pipeline import (
    DiscourseProposal,
    MultimodalSummaryProposal,
    PipelineContext,
    run_canonical_pipeline,
)
from laclaugpt_data_analysis.dna_statement_coding import (
    DNAConceptCandidate,
    DNAEntityCandidate,
    DNAStatementBatch,
    DNAStatementCandidate,
    dna_statement_coding_config,
)
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.prompt_library import load_prompt


class SequencedProvider:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.requests.append(request)
        payload = self.payloads.pop(0)
        return LLMResponse(
            content=payload.model_dump_json(),
            provenance=LLMCallProvenance(
                requested_mode="local",
                requested_model=request.model,
                resolved_model=request.model,
                actual_mode="local",
                actual_model=request.model,
                endpoint="fake",
            ),
        )


def record(text: str) -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/dna/1",
        source_native_ids={"synthetic": "doc-1"},
        raw_capture={"payload": {"synthetic": True}},
        source={
            "platform": "synthetic",
            "language": "en",
            "created_at": datetime(2026, 9, 17, tzinfo=UTC),
        },
        content={"text": text},
    )


def summary() -> MultimodalSummaryProposal:
    return MultimodalSummaryProposal(summary="Synthetic statement source.")


def discourse() -> DiscourseProposal:
    return DiscourseProposal(populist=False, non_populist_reason="No populist relation evidenced.")


def candidate(
    text: str,
    *,
    agreement: bool | None = True,
    agreement_status: str = "coded",
    person: str | None = "Ada Example",
    organization: str | None = "Example Institute",
) -> DNAStatementBatch:
    quote = "Open-source AI models should remain legally available"
    start = text.index(quote) if quote in text else None
    return DNAStatementBatch(
        statements=[
            DNAStatementCandidate(
                person=DNAEntityCandidate(label=person) if person else None,
                organization=DNAEntityCandidate(label=organization) if organization else None,
                concept=DNAConceptCandidate(
                    id="concept:open-ai-legal",
                    label="Open-source AI models should remain legally available",
                    original_text=quote,
                ),
                agreement=agreement,
                agreement_status=agreement_status,
                evidence_text=quote,
                start=start,
                stop=(start + len(quote)) if start is not None else None,
                confidence=0.93,
            )
        ]
    )


def test_prompt_library_is_versioned_and_forbids_laclau_agreement_mapping() -> None:
    system = load_prompt("dna.statement_coding_system", version="v1")
    task = load_prompt("dna.statement_coding", version="v1")
    rendered = task.render(
        concept_mode="codebook_or_provisional",
        require_binary_agreement="false",
        duplicate_policy="preserve",
    )

    assert len(system.sha256) == 64
    assert "agreement=true" in system.text
    assert "Laclaudian" in system.text
    assert "Never infer a DNA agreement value" in rendered.text


def test_feature_is_disabled_by_default_with_zero_extra_model_calls() -> None:
    provider = SequencedProvider([summary(), discourse()])
    result = run_canonical_pipeline(
        record("No DNA coding requested."),
        provider=provider,
        context=PipelineContext(project_config={"project": "ai26"}),
        project_profile="ai26",
        model="gemma4:test",
    )

    assert len(provider.requests) == 2
    assert "dna_statement_coding" not in result.intermediate.stage_outputs
    assert dna_statement_coding_config({}).enabled is False


def test_enabled_pipeline_stage_projects_person_concept_agreement_and_exact_offsets() -> None:
    text = "Ada Example said: Open-source AI models should remain legally available."
    provider = SequencedProvider([summary(), discourse(), candidate(text)])
    result = run_canonical_pipeline(
        record(text),
        provider=provider,
        context=PipelineContext(
            codebook_revision="ai26-codebook-v2",
            project_config={
                "analysis": {
                    "dna_statement_coding": {
                        "enabled": True,
                        "model": "gemma4:12b",
                        "prompt_version": "v1",
                        "require_binary_agreement": False,
                        "duplicate_policy": "preserve",
                    }
                }
            },
        ),
        project_profile="ai26",
        model="fallback-model",
    )

    assert len(provider.requests) == 3
    assert provider.requests[-1].model == "gemma4:12b"
    stage = result.intermediate.stage_outputs["dna_statement_coding"][-1]
    statement = stage["proposal"]["statements"][0]
    assert statement["actor_name"] == "Ada Example"
    assert statement["concept_id"] == "concept:open-ai-legal"
    assert statement["stance"] == "support"
    assert statement["metadata"]["agreement"] is True
    assert statement["metadata"]["organization"]["label"] == "Example Institute"
    assert statement["evidence"]["exact"] is True
    assert text[statement["evidence"]["start_char"] : statement["evidence"]["end_char"]] == statement["evidence"]["quote"]
    assert statement["metadata"]["duplicate_key"].startswith("synthetic:doc-1|")
    assert statement["codebook_version"] == "ai26-codebook-v2"
    assert result.analysis.plugin_results["dna_statement_coding"]["proposal"]["statements"]


def test_ambiguous_stance_abstains_instead_of_forcing_binary_agreement() -> None:
    text = "Ada Example said: Open-source AI models should remain legally available."
    batch = candidate(text, agreement=None, agreement_status="ambiguous")
    provider = SequencedProvider([summary(), discourse(), batch])
    result = run_canonical_pipeline(
        record(text),
        provider=provider,
        context=PipelineContext(
            project_config={"analysis": {"dna_statement_coding": {"enabled": True}}}
        ),
        project_profile="ai26",
    )
    statement = result.intermediate.stage_outputs["dna_statement_coding"][-1]["proposal"]["statements"][0]
    assert statement["stance"] == "unknown"
    assert statement["abstained"] is True
    assert statement["metadata"]["agreement"] is None
    assert statement["metadata"]["agreement_status"] == "ambiguous"


def test_organization_can_speak_without_named_person() -> None:
    text = "Example Institute states: Open-source AI models should remain legally available."
    provider = SequencedProvider(
        [summary(), discourse(), candidate(text, person=None, organization="Example Institute")]
    )
    result = run_canonical_pipeline(
        record(text),
        provider=provider,
        context=PipelineContext(
            project_config={"analysis": {"dna_statement_coding": {"enabled": True}}}
        ),
        project_profile="ai26",
    )
    statement = result.intermediate.stage_outputs["dna_statement_coding"][-1]["proposal"]["statements"][0]
    assert statement["actor_name"] == "Example Institute"
    assert statement["metadata"]["person"] is None


@pytest.mark.parametrize(
    "text, quote",
    [
        (
            "Ada sanoi: Avoimen lähdekoodin tekoälymallien tulee säilyä laillisesti saatavilla.",
            "Avoimen lähdekoodin tekoälymallien tulee säilyä laillisesti saatavilla",
        ),
        (
            "Ada powiedziała: Modele AI open source powinny pozostać legalnie dostępne.",
            "Modele AI open source powinny pozostać legalnie dostępne",
        ),
        (
            "Ada said: Open-source AI models should remain legally available.",
            "Open-source AI models should remain legally available",
        ),
    ],
)
def test_multilingual_unicode_offsets_are_repaired_from_exact_evidence(text: str, quote: str) -> None:
    batch = DNAStatementBatch(
        statements=[
            DNAStatementCandidate(
                person=DNAEntityCandidate(label="Ada"),
                concept=DNAConceptCandidate(label="Open-source AI models should remain legally available"),
                agreement=True,
                agreement_status="coded",
                evidence_text=quote,
                start=0,
                stop=len(quote),
            )
        ]
    )
    provider = SequencedProvider([summary(), discourse(), batch])
    result = run_canonical_pipeline(
        record(text),
        provider=provider,
        context=PipelineContext(
            project_config={"analysis": {"dna_statement_coding": {"enabled": True}}}
        ),
        project_profile="ai26",
    )
    evidence = result.intermediate.stage_outputs["dna_statement_coding"][-1]["proposal"]["statements"][0]["evidence"]
    assert evidence["exact"] is True
    assert text[evidence["start_char"] : evidence["end_char"]] == quote


def test_unlocatable_evidence_is_kept_for_review_not_claimed_exact() -> None:
    text = "Ada Example supports open models."
    batch = candidate("Open-source AI models should remain legally available")
    provider = SequencedProvider([summary(), discourse(), batch])
    result = run_canonical_pipeline(
        record(text),
        provider=provider,
        context=PipelineContext(
            project_config={"analysis": {"dna_statement_coding": {"enabled": True}}}
        ),
        project_profile="ai26",
    )
    statement = result.intermediate.stage_outputs["dna_statement_coding"][-1]["proposal"]["statements"][0]
    assert statement["evidence"]["exact"] is False
    assert statement["validation_status"] == "needs_review"
