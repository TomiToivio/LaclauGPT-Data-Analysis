from __future__ import annotations

from datetime import UTC, datetime

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.canonical_pipeline import (
    DiscourseProposal,
    MultimodalSummaryProposal,
    PipelineContext,
)
from laclaugpt_data_analysis.contextual_pipeline import run_contextual_canonical_pipeline
from laclaugpt_data_analysis.critical_ai import CriticalAIAnalysis
from laclaugpt_data_analysis.dna_statement_coding import DNAStatementBatch
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse


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


def test_contextual_runner_executes_enabled_dna_and_critical_ai_stages() -> None:
    record = CanonicalRecord(
        source_url="https://example.invalid/issue-74/1",
        raw_capture={"payload": {"synthetic": True}},
        source={"platform": "synthetic", "created_at": datetime(2026, 9, 17, tzinfo=UTC)},
        content={"text": "AI policy actors debate whether open models should remain available."},
    )
    provider = SequencedProvider(
        [
            MultimodalSummaryProposal(summary="Synthetic AI policy source."),
            DiscourseProposal(populist=False, non_populist_reason="No populist relation evidenced."),
            DNAStatementBatch(statements=[]),
            CriticalAIAnalysis(overall_summary="Synthetic Critical AI analysis."),
        ]
    )
    caller_context = PipelineContext(
        config_revision="cfg-r1",
        codebook_revision="cb-r1",
        context_revision="ctx-r1",
        project_config_revision="project-r1",
        project_config={
            "analysis": {
                "dna_statement_coding": {"enabled": True, "prompt_version": "v1"},
                "critical_ai": {"enabled": True, "prompt_version": "v1"},
            }
        },
    )

    result = run_contextual_canonical_pipeline(
        record,
        provider=provider,
        project_id="ai26",
        caller_context=caller_context,
        project_profile="ai26",
        model="gemma4:test",
    )

    assert len(provider.requests) == 4
    assert "dna_statement_coding" in result.intermediate.stage_outputs
    assert "critical_ai_analysis" in result.intermediate.stage_outputs
    assert "Discourse Network Analysis" in provider.requests[2].system
    assert "Critical AI Studies" in provider.requests[3].system
    assert result.intermediate.stage_outputs["critical_ai_analysis"][-1]["model_run"][
        "project_config_revision"
    ] == "project-r1"
