from __future__ import annotations

import json
from datetime import UTC, datetime

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.canonical_pipeline import (
    DiscourseProposal,
    MultimodalFrameProposal,
    MultimodalSummaryProposal,
    PipelineContext,
    prompt_ids_for_stage,
    run_canonical_pipeline,
)
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.prompt_library import load_prompt
from laclaugpt_data_analysis.social_semiotic import (
    EvidencePointer,
    IntermodalRelation,
    UncertaintyObservation,
)


class SequencedProvider:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.requests.append(request)
        payload = self.payloads.pop(0)
        return LLMResponse(
            content=payload.model_dump_json() if hasattr(payload, "model_dump_json") else json.dumps(payload),
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
    system = load_prompt("multimodal.system", version="v2")
    frame = load_prompt("multimodal.frame_analysis", version="v2")
    summary = load_prompt("multimodal.summary_analysis", version="v2")

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

    # Historical resources remain loadable for reproducibility.
    assert load_prompt("multimodal.system", version="v1").version == "v1"
    assert load_prompt("laclau.frame_analysis", version="v1").version == "v1"


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
        "ep24.frame_analysis",
    )


def test_multimodal_schemas_preserve_uncertainty_without_political_labels() -> None:
    frame = MultimodalFrameProposal(
        material_canvas_organisation=["Split-screen layout"],
        uncertainty=[
            UncertaintyObservation(
                category="visual",
                description="The logo is unreadable.",
                confidence="low",
            )
        ],
    )
    assert frame.uncertainty
    assert "candidate_signifiers" not in MultimodalFrameProposal.model_fields
    assert "rhetorical_cues" not in MultimodalFrameProposal.model_fields

    summary = MultimodalSummaryProposal(
        summary="The spoken claim and chart point in different directions.",
        intermodal_relations=[
            IntermodalRelation(
                relation_type="conflict",
                modes=["linguistic", "visual"],
                description="Speech endorses the claim; chart annotation qualifies it.",
                confidence="high",
            )
        ],
        uncertainty=[
            UncertaintyObservation(
                category="source_context",
                description="The chart source is not visible.",
                confidence="low",
            )
        ],
    )
    assert summary.intermodal_relations
    assert "candidate_signifiers" not in MultimodalSummaryProposal.model_fields
    assert "candidate_frontiers" not in MultimodalSummaryProposal.model_fields
    assert "sentiment_observations" not in MultimodalSummaryProposal.model_fields


def test_ai26_pipeline_persists_social_semiotics_and_run_provenance() -> None:
    frame = MultimodalFrameProposal(
        material_canvas_organisation=["Chart beside speaker video"],
        scene_and_participants=["One visible speaker"],
        visible_text=["Synthetic benchmark"],
        semiotic_contribution="The chart visually contextualises the spoken technical claim.",
        evidence=[
            EvidencePointer(
                evidence_id="frame:1",
                modality="visual",
                frame_id="frame-001",
                timestamp_start=12.5,
                confidence="high",
            )
        ],
        uncertainty=[
            UncertaintyObservation(
                category="visual",
                description="Chart source is not visible.",
                confidence="low",
            )
        ],
    )
    summary = MultimodalSummaryProposal(
        summary="A technical AI claim is presented through speech and a benchmark chart.",
        narrative="The speaker introduces the claim, then the chart supplies numerical context.",
        modalities_present=["linguistic", "visual", "temporal_editing"],
        semiotic_modes=["speech", "written chart labels", "video"],
        cross_modal_relations=["The chart elaborates the spoken claim without fully proving it."],
        intermodal_relations=[
            IntermodalRelation(
                relation_type="elaboration",
                modes=["linguistic", "visual"],
                description="The chart adds numerical context to the spoken claim.",
                confidence="high",
            )
        ],
        topics=["AI benchmarks"],
        entities=["Synthetic Lab"],
        claims=["The speaker claims a model improved on a benchmark."],
        cross_modal_synthesis="Speech presents the claim and the chart adds numerical context.",
        uncertainty=[
            UncertaintyObservation(
                category="source_context",
                description="The benchmark methodology is not visible in the item.",
                confidence="low",
            )
        ],
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
    assert "Multimodal Social-Semiotic Pre-Analysis" in provider.requests[0].system
    assert "frame-001" in provider.requests[0].user
    assert "12.5" in provider.requests[0].user
    assert "AI26 source context only; remain descriptive." in provider.requests[0].user
    assert "denotative_description" in provider.requests[1].user
    assert "Laclau" in provider.requests[2].system

    frame_result = result.intermediate.frame_analysis[0]
    prompt_ids = [item["prompt_id"] for item in frame_result["prompt_resources"]]
    assert prompt_ids == ["multimodal.system", "multimodal.frame_analysis"]
    assert all(item["version"] == "v2" for item in frame_result["prompt_resources"])
    assert "multimodal_synthesis" in result.intermediate.stage_outputs
    assert "castells_context" not in result.intermediate.stage_outputs
    assert "discourse_analysis" in result.intermediate.stage_outputs
    assert "summary_preanalysis" not in result.intermediate.stage_outputs
    assert result.analysis.signifiers == []
    assert "benchmark methodology" in result.analysis.uncertainty[0]

    for run in result.analysis.model_runs:
        assert run["codebook_revision"] == "codebook-r4"
        assert run["context_revision"] == "context-r2"
        assert run["project_config_revision"] == "project-config-r3"
        assert len(run["project_config_sha256"]) == 64
        assert run["prompt_resources"]
        assert run["actual_model"] == "fake-model"


def test_ai26_pipeline_accepts_model_null_frame_and_known_source_ref_typo() -> None:
    summary_payload = {
        "summary": "A text-derived AI claim with no frame evidence.",
        "modalities_present": ["linguistic"],
        "evidence": [
            {
                "evidence_id": "text:legacy:1",
                "modality": "linguistic",
                "source__ref": "content.text",
                "exact_text": "A speaker discusses an AI system while a chart is shown.",
                "frame_id": None,
                "uncertainty": "This pointer is text-derived rather than frame-derived.",
            }
        ],
    }
    provider = SequencedProvider([MultimodalFrameProposal(), summary_payload, DiscourseProposal()])

    result = run_canonical_pipeline(
        multimodal_record(),
        provider=provider,
        context=PipelineContext(
            project_config={"project": "ai26", "multimodal": True},
        ),
        model="fake-model",
        project_profile="ai26",
    )

    assert result.analysis.status == "analyzed"
    proposal = result.intermediate.stage_outputs["multimodal_synthesis"][-1]["proposal"]
    assert proposal["evidence"][0]["source_ref"] == "content.text"
    assert proposal["evidence"][0]["frame_id"] == ""
    assert proposal["evidence"][0]["uncertainty"] == (
        "This pointer is text-derived rather than frame-derived."
    )
