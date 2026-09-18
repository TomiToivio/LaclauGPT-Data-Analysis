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
from laclaugpt_data_analysis.critical_ai import (
    CriticalAIAnalysis,
    CriticalAIFinding,
    CriticalAIInterpretation,
    CriticalAISourceEvidence,
    critical_ai_config,
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


def record(text: str = "The company says adoption of its AI platform is unavoidable.") -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/critical-ai/1",
        raw_capture={"payload": {"synthetic": True}},
        source={"platform": "synthetic", "created_at": datetime(2026, 9, 17, tzinfo=UTC)},
        content={"text": text},
    )


def summary() -> MultimodalSummaryProposal:
    return MultimodalSummaryProposal(
        summary="A company makes a claim about adoption of an AI platform.",
        narrative="The item presents the company's claim without independent verification.",
        claims=["The company describes adoption as unavoidable."],
        later_analysis_cues=["The inevitability wording can be examined downstream."],
    )


def discourse() -> DiscourseProposal:
    return DiscourseProposal(
        populist=False,
        non_populist_reason="No collective Us/frontier relation is evidenced.",
    )


def critical() -> CriticalAIAnalysis:
    return CriticalAIAnalysis(
        findings=[
            CriticalAIFinding(
                dimension="technological_myths",
                claim="The company frames adoption as technologically inevitable.",
                status="supported",
                source_evidence=[
                    CriticalAISourceEvidence(
                        quote_or_span="adoption of its AI platform is unavoidable"
                    )
                ],
                interpretation=CriticalAIInterpretation(
                    lens="technological inevitability",
                    reasoning_summary="The source uses explicit inevitability language.",
                    alternative_reading="The wording may be promotional exaggeration rather than a literal forecast.",
                ),
            )
        ],
        overall_summary="The item contains an explicit inevitability frame; wider structural claims are not established.",
        human_review_priorities=["Verify the exact quotation in the original source."],
    )


def test_critical_ai_prompt_library_is_versioned_and_explicit() -> None:
    system = load_prompt("critical_ai.system", version="v1")
    task = load_prompt("critical_ai.analysis", version="v1")

    assert len(system.sha256) == 64
    assert len(task.sha256) == 64
    assert "sociotechnical assemblage" in system.text
    assert "SOURCE_EVIDENCE" in system.text
    rendered = task.render(
        evidence_mode="strict",
        include_prior_laclau="true",
        include_prior_dna="true",
        include_rag="true",
        include_periodic_context="true",
    )
    assert "technological inevitability" in rendered.text
    assert "Never output a criticality" in rendered.text


def test_feature_is_disabled_by_default_and_has_zero_extra_model_calls() -> None:
    provider = SequencedProvider([summary(), discourse()])
    result = run_canonical_pipeline(
        record(),
        provider=provider,
        context=PipelineContext(project_config={"project": "ai26"}),
        project_profile="ai26",
        model="gemma4:test",
    )

    assert len(provider.requests) == 2
    assert "critical_ai_analysis" not in result.intermediate.stage_outputs
    assert critical_ai_config({}).enabled is False


def test_enabled_stage_uses_project_selected_model_and_links_source_evidence() -> None:
    provider = SequencedProvider([summary(), discourse(), critical()])
    result = run_canonical_pipeline(
        record(),
        provider=provider,
        context=PipelineContext(
            project_context="AI26 synthetic context",
            rag_context="External context that must not become source evidence.",
            situational_context="Previous-day trend context.",
            project_config_revision="ai26-r1",
            codebook_revision="cb-r2",
            project_config={
                "project": "ai26",
                "analysis_phase": 2,
                "analysis": {
                    "critical_ai": {
                        "enabled": True,
                        "provider": "ollama",
                        "model": "gemma4:12b",
                        "prompt_version": "v1",
                        "include_prior_laclau": True,
                        "include_prior_dna": True,
                        "include_rag": True,
                        "include_periodic_context": True,
                        "evidence_mode": "strict",
                    }
                },
            },
        ),
        project_profile="ai26",
        model="fallback-model",
    )

    assert len(provider.requests) == 3
    critical_request = provider.requests[-1]
    assert critical_request.model == "gemma4:12b"
    assert "[RAG CONTEXT]" in critical_request.user
    assert "External context that must not become source evidence" in critical_request.user
    assert "PRIOR_ANALYSIS proposals, not SOURCE_EVIDENCE" in critical_request.user
    assert "Critical AI Studies" in critical_request.system

    stage = result.intermediate.stage_outputs["critical_ai_analysis"][-1]
    finding = stage["proposal"]["findings"][0]
    assert finding["finding_id"] == "critical-ai:1"
    assert finding["evidence_ids"]
    assert stage["configuration"]["enabled"] is True
    assert stage["model_run"]["actual_model"] == "gemma4:12b"
    assert stage["model_run"]["codebook_revision"] == "cb-r2"
    assert len(stage["model_run"]["project_config_sha256"]) == 64

    evidence = result.evidence[-1]
    assert evidence.quote == "adoption of its AI platform is unavoidable"
    assert evidence.metadata["analysis_method"] == "critical_ai_studies"
    assert evidence.metadata["dimension"] == "technological_myths"


def test_rag_and_periodic_context_can_be_excluded_without_removing_source() -> None:
    provider = SequencedProvider([summary(), discourse(), critical()])
    run_canonical_pipeline(
        record(),
        provider=provider,
        context=PipelineContext(
            rag_context="RAG SHOULD NOT APPEAR",
            situational_context="PERIODIC SHOULD NOT APPEAR",
            project_config={
                "analysis_phase": 2,
                "analysis": {
                    "critical_ai": {
                        "enabled": True,
                        "include_rag": False,
                        "include_periodic_context": False,
                    }
                },
            },
        ),
        project_profile="ai26",
        model="gemma4:test",
    )
    request = provider.requests[-1]
    assert "RAG SHOULD NOT APPEAR" not in request.user
    assert "PERIODIC SHOULD NOT APPEAR" not in request.user
    assert "adoption of its AI platform is unavoidable" in request.user


@pytest.mark.parametrize(
    "text, quote",
    [
        ("Tekoälyn käyttöönotto on väistämätöntä, yhtiö väittää.", "väistämätöntä"),
        ("Firma twierdzi, że wdrożenie AI jest nieuniknione.", "nieuniknione"),
        ("The firm says AI adoption is inevitable.", "inevitable"),
    ],
)
def test_multilingual_source_material_is_preserved_in_critical_ai_prompt(text: str, quote: str) -> None:
    provider = SequencedProvider([summary(), discourse(), CriticalAIAnalysis()])
    run_canonical_pipeline(
        record(text),
        provider=provider,
        context=PipelineContext(
            project_config={"analysis": {"critical_ai": {"enabled": True}}}
        ),
        project_profile="ai26",
        model="gemma4:test",
    )
    assert quote in provider.requests[-1].user
