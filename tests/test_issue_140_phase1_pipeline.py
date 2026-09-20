from __future__ import annotations

from datetime import UTC, datetime

from laclaugpt_data_analysis.canonical import CanonicalRecord, ContentSection, SourceSection
from laclaugpt_data_analysis.canonical_pipeline import (
    DiscourseProposal,
    MultimodalSummaryProposal,
    PipelineContext,
    prompt_ids_for_stage,
    run_canonical_pipeline,
)
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
                requested_model="fake-model",
                resolved_model="fake-model",
                actual_mode="local",
                actual_model="fake-model",
                endpoint="fake",
            ),
        )


def _record(*, with_frame: bool) -> CanonicalRecord:
    frames = (
        [{"id": "frame-1", "timestamp_seconds": 1.5, "description": "synthetic"}]
        if with_frame
        else []
    )
    return CanonicalRecord(
        source_url="https://example.test/item",
        source=SourceSection(platform="test", created_at=datetime(2026, 9, 18, tzinfo=UTC)),
        content=ContentSection(text="AI policy debate with a concrete demand.", frames=frames),
    )


def _ctx(**analysis):
    defaults = {
        "laclau": True,
        "multimodal": True,
        "topics": True,
        "entities": True,
        "sentiment": True,
        "sociotechnical_imaginaries": True,
        "sna": {"enabled": False, "phase": 2, "experimental": True, "optional": True},
        "ant": {"enabled": False, "phase": 2, "experimental": True, "optional": True},
        "valueflows": {"enabled": False, "phase": 2, "experimental": True, "optional": True},
        "dna_statement_coding": {"enabled": False},
        "critical_ai": {"enabled": False},
    }
    defaults.update(analysis)
    return PipelineContext(project_config={"analysis_phase": 1, "analysis": defaults})


def test_phase1_text_only_order_skips_frame_and_postprocesses_last():
    provider = SequencedProvider([
        MultimodalSummaryProposal(summary="summary", topics=["AI policy"]),
        DiscourseProposal(),
    ])
    result = run_canonical_pipeline(
        _record(with_frame=False),
        provider=provider,
        context=_ctx(),
        project_profile="ai26",
        model="fake-model",
    )

    assert len(provider.requests) == 2
    outputs = result.intermediate.stage_outputs
    assert "preprocess_contract" in outputs
    assert "frame_analysis_skipped" in outputs
    assert "multimodal_synthesis" in outputs
    assert "discourse_analysis" in outputs
    assert "postprocess" in outputs
    assert outputs["frame_analysis_skipped"][-1]["reason"] == "no_materialized_image_or_video_frames"
    assert outputs["postprocess"][-1]["validated"] is True
    assert outputs["postprocess"][-1]["source_stages"] == ["summary", "discourse"]


def test_phase1_multimodal_order_runs_frame_before_summary_and_discourse():
    from laclaugpt_data_analysis.canonical_pipeline import MultimodalFrameProposal

    provider = SequencedProvider([
        MultimodalFrameProposal(scene_and_participants=["speaker"]),
        MultimodalSummaryProposal(summary="summary"),
        DiscourseProposal(),
    ])
    result = run_canonical_pipeline(
        _record(with_frame=True),
        provider=provider,
        context=_ctx(),
        project_profile="ai26",
        model="fake-model",
    )
    assert len(provider.requests) == 3
    assert result.intermediate.frame_analysis
    assert "multimodal_synthesis" in result.intermediate.stage_outputs
    assert "discourse_analysis" in result.intermediate.stage_outputs
    assert "postprocess" in result.intermediate.stage_outputs


def test_phase2_methods_are_off_by_default_in_phase1_context():
    ctx = _ctx()
    assert ctx.project_config["analysis"]["dna_statement_coding"]["enabled"] is False
    assert ctx.project_config["analysis"]["critical_ai"]["enabled"] is False
    assert ctx.project_config["analysis"]["sna"]["enabled"] is False


def test_ep24_and_ai26_prompt_profiles_are_distinct():
    assert prompt_ids_for_stage("ep24", "frame") == ("laclau.system", "ep24.frame_analysis")
    assert prompt_ids_for_stage("ep24", "summary") == ("laclau.system", "ep24.summary_analysis")
    assert prompt_ids_for_stage("ep24", "discourse") == ("laclau.system", "ep24.laclau_analysis")
    assert prompt_ids_for_stage("ai26", "frame") == (
        "multimodal.system",
        "multimodal.frame_analysis",
    )
    assert prompt_ids_for_stage("ai26", "summary") == (
        "multimodal.system",
        "multimodal.summary_analysis",
    )
    assert prompt_ids_for_stage("ai26", "discourse") == (
        "laclau.system",
        "laclau.discourse_analysis",
    )


def test_phase1_gate_blocks_phase2_module_even_when_flag_is_accidentally_enabled():
    ctx = _ctx(sna={"enabled": True, "phase": 2, "experimental": True, "optional": True})
    from laclaugpt_data_analysis.canonical_pipeline import _effective_stage_set
    assert "sna" not in _effective_stage_set(ctx)
