from __future__ import annotations

from datetime import UTC, datetime

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.canonical_pipeline import (
    CastellsContextProposal,
    DiscourseProposal,
    MultimodalFrameProposal,
    MultimodalSummaryProposal,
    PipelineContext,
    prompt_ids_for_stage,
    run_canonical_pipeline,
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
                requested_model="fake-model",
                resolved_model="fake-model",
                actual_mode="local",
                actual_model="fake-model",
                endpoint="fake",
            ),
        )


def multimodal_record() -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/ai26/video/1",
        raw_capture={"payload": {"synthetic": True}},
        source={
            "platform": "synthetic-video",
            "created_at": datetime(2026, 9, 17, 9, 0, tzinfo=UTC),
        },
        content={
            "text": "A speaker discusses an AI system while a chart is shown.",
            "frames": [
                {
                    "id": "frame-001",
                    "timestamp_seconds": 12.5,
                    "description": "Synthetic keyframe",
                }
            ],
        },
    )


def test_multimodal_prompt_family_loads_hashes_and_renders() -> None:
    system = load_prompt("multimodal.system", version="v1")
    frame = load_prompt("multimodal.frame_analysis", version="v1")
    summary = load_prompt("multimodal.summary_analysis", version="v1")

    assert len(system.sha256) == 64
    assert len(frame.sha256) == 64
    assert len(summary.sha256) == 64
    rendered = frame.render(
        frame_id="frame-001",
        timestamp_seconds=12.5,
        project_note="AI26 relevance guide only",
    )
    assert "frame-001" in rendered.text
    assert "12.5" in rendered.text
    assert "AI26 relevance guide only" in rendered.text

    # Historical prompt resources remain loadable for reproducibility.
    assert load_prompt("laclau.frame_analysis", version="v1").version == "v1"
    assert load_prompt("laclau.summary_analysis", version="v1").version == "v1"


def test_ai26_stage_selection_separates_multimodal_and_discourse_prompts() -> None:
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
    assert prompt_ids_for_stage("ep24", "frame") == (
        "laclau.system",
        "laclau.frame_analysis",
    )


def test_multimodal_schemas_allow_uncertainty_without_ideological_labels() -> None:
    frame = MultimodalFrameProposal(
        material_canvas_organisation=["Split-screen layout"],
        uncertainty=["The logo is unreadable."],
    )
    assert frame.uncertainty
    assert "candidate_signifiers" not in MultimodalFrameProposal.model_fields
    assert "rhetorical_cues" not in MultimodalFrameProposal.model_fields

    summary = MultimodalSummaryProposal(
        summary="The spoken claim and chart point in different directions.",
        cross_modal_relations=["Speech endorses the claim; chart annotation qualifies it."],
        castells_context=CastellsContextProposal(),
        later_analysis_cues=["Later discourse analysis may examine how control is articulated."],
    )
    assert summary.cross_modal_relations
    assert summary.castells_context.networks_relations == []
    assert "candidate_signifiers" not in MultimodalSummaryProposal.model_fields
    assert "candidate_frontiers" not in MultimodalSummaryProposal.model_fields


def test_ai26_pipeline_persists_multimodal_castells_and_run_provenance() -> None:
    frame = MultimodalFrameProposal(
        material_canvas_organisation=["Chart beside speaker video"],
        scene_and_participants=["One visible speaker"],
        visible_text=["Synthetic benchmark"],
        semiotic_contribution="The chart visually contextualises the spoken technical claim.",
        uncertainty=["Chart source is not visible."],
    )
    summary = MultimodalSummaryProposal(
        summary="A technical AI claim is presented through speech and a benchmark chart.",
        narrative="The speaker introduces the claim, then the chart supplies numerical context.",
        semiotic_modes=["speech", "written chart labels", "video"],
        cross_modal_relations=["The chart elaborates the spoken claim without fully proving it."],
        topics=["AI benchmarks"],
        entities=["Synthetic Lab"],
        claims=["The speaker claims a model improved on a benchmark."],
        sentiment_observations=["Positive evaluation targets the reported benchmark result."],
        castells_context=CastellsContextProposal(
            actors_organisations_institutions=["Synthetic Lab is named in source context."],
            flows=["Benchmark information is communicated through the video."],
            nodes_hubs_channels=["The video platform functions as the communication channel."],
            networks_relations=[],
            uncertainty=["No wider organisational network is established by this item."],
        ),
        later_analysis_cues=["How is technical performance articulated with social authority?"],
        uncertainty=["The benchmark methodology is not visible in the item."],
    )
    discourse = DiscourseProposal(
        populist=False,
        non_populist_reason="No collective Us/frontier pair is established.",
        abstentions=["No formation classification from the multimodal pre-analysis alone."],
    )
    provider = SequencedProvider([frame, summary, discourse])

    result = run_canonical_pipeline(
        multimodal_record(),
        provider=provider,
        context=PipelineContext(
            project_context="AI26 synthetic public context",
            config_revision="config-r7",
            codebook_revision="codebook-r4",
            context_revision="context-r2",
            project_config_revision="project-config-r3",
            project_config={"project": "ai26", "multimodal": True},
        ),
        model="fake-model",
        project_profile="ai26",
    )

    assert len(provider.requests) == 3
    assert "Multimodal pre-analysis method" in provider.requests[0].system
    assert "frame-001" in provider.requests[0].user
    assert "12.5" in provider.requests[0].user
    assert "AI26 relevance guide only" in provider.requests[0].user
    assert "Light Castells-style sociological context" in provider.requests[1].user
    assert "Laclau" in provider.requests[2].system

    frame_result = result.intermediate.frame_analysis[0]
    prompt_ids = [item["prompt_id"] for item in frame_result["prompt_resources"]]
    assert prompt_ids == ["multimodal.system", "multimodal.frame_analysis"]
    assert "multimodal_synthesis" in result.intermediate.stage_outputs
    assert "castells_context" in result.intermediate.stage_outputs
    assert "discourse_analysis" in result.intermediate.stage_outputs
    assert "summary_preanalysis" not in result.intermediate.stage_outputs

    castells = result.intermediate.stage_outputs["castells_context"][-1]["proposal"]
    assert castells["networks_relations"] == []
    assert "No wider organisational network" in castells["uncertainty"][0]
    assert "Later analysis cues" in result.human_readable.markdown
    assert result.analysis.signifiers == []

    for run in result.analysis.model_runs:
        assert run["codebook_revision"] == "codebook-r4"
        assert run["context_revision"] == "context-r2"
        assert run["project_config_revision"] == "project-config-r3"
        assert len(run["project_config_sha256"]) == 64
        assert run["prompt_resources"]
        assert run["actual_model"] == "fake-model"
