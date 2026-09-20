from __future__ import annotations

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.canonical_pipeline import (
    DiscourseProposal,
    PipelineContext,
    run_canonical_pipeline,
)
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.modality_routing import (
    build_modality_plan,
    ensure_still_image_frames,
)
from laclaugpt_data_analysis.social_semiotic import (
    MultimodalFrameProposal,
    MultimodalSummaryProposal,
)


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
                requested_model="fake",
                resolved_model="fake",
                actual_mode="local",
                actual_model="fake",
                endpoint="fake",
            ),
        )


def context() -> PipelineContext:
    return PipelineContext(
        project_config={
            "analysis_phase": 1,
            "analysis": {"laclau": True},
        }
    )


def test_text_only_pipeline_never_invokes_visual_stage() -> None:
    provider = SequencedProvider(
        [
            MultimodalSummaryProposal(summary="Text-only descriptive pre-analysis."),
            DiscourseProposal(),
        ]
    )
    record = CanonicalRecord(
        source_url="https://example.invalid/text-only",
        content={"text": "Only source text is present."},
    )

    result = run_canonical_pipeline(
        record,
        provider=provider,
        context=context(),
        model="fake",
        project_profile="ai26",
    )

    assert len(provider.requests) == 2
    assert all(not request.images for request in provider.requests)
    plan = result.intermediate.stage_outputs["modality_plan"][-1]
    assert plan["is_text_only"] is True
    assert plan["needs_frame_analysis"] is False
    assert result.intermediate.frame_analysis == []
    skipped = result.intermediate.stage_outputs["frame_analysis_skipped"][-1]
    assert skipped["reason"] == "no_materialized_image_or_video_frames"


def test_materialized_still_image_runs_visual_analysis_without_video_extraction(tmp_path) -> None:
    image = tmp_path / "still.jpg"
    image.write_bytes(b"synthetic-image-bytes")
    provider = SequencedProvider(
        [
            MultimodalFrameProposal(denotation=["A synthetic still image."]),
            MultimodalSummaryProposal(summary="Image-aware descriptive pre-analysis."),
            DiscourseProposal(),
        ]
    )
    record = CanonicalRecord(
        source_url="https://example.invalid/image",
        content={
            "text": "Caption",
            "media_references": [
                {
                    "kind": "image",
                    "media_type": "image/jpeg",
                    "ref": "source-image-1",
                    "local_ref": str(image),
                }
            ],
        },
    )

    result = run_canonical_pipeline(
        record,
        provider=provider,
        context=context(),
        model="fake",
        project_profile="ai26",
    )

    assert len(provider.requests) == 3
    assert provider.requests[0].images == (str(image),)
    assert result.content.frames[0].timestamp_seconds == 0
    assert result.content.frames[0].description == "Materialized still image"
    plan = result.intermediate.stage_outputs["modality_plan"][-1]
    assert plan["has_image"] is True
    assert plan["has_video"] is False
    assert plan["needs_frame_analysis"] is True
    assert result.intermediate.stage_outputs["multimodal_visibility"][-1]["attachments"]


def test_remote_image_reference_alone_is_not_direct_visual_evidence() -> None:
    record = CanonicalRecord(
        source_url="https://example.invalid/unmaterialized",
        content={
            "text": "Caption only until media is materialized.",
            "media_references": [
                {
                    "kind": "image",
                    "media_type": "image/jpeg",
                    "ref": "https://cdn.invalid/image.jpg",
                    "url": "https://cdn.invalid/image.jpg",
                }
            ],
        },
    )
    ensure_still_image_frames(record)
    plan = build_modality_plan(record)

    assert plan.declared_images == 1
    assert plan.materialized_images == 0
    assert plan.has_image is False
    assert plan.has_frames is False
    assert plan.needs_frame_analysis is False


def test_audio_only_never_becomes_visual() -> None:
    record = CanonicalRecord(
        source_url="https://example.invalid/audio",
        content={
            "media_references": [
                {
                    "kind": "audio",
                    "media_type": "audio/mpeg",
                    "ref": "audio-1",
                    "local_ref": "/synthetic/materialized/audio.mp3",
                }
            ],
            "transcripts": [
                {"id": "asr-1", "text": "Spoken words", "language": "en"}
            ],
        },
    )
    plan = build_modality_plan(record)

    assert plan.has_audio is True
    assert plan.has_transcript is True
    assert plan.has_visual_media is False
    assert plan.needs_frame_analysis is False


def test_video_frames_activate_visual_analysis_only_after_frames_exist() -> None:
    record = CanonicalRecord(
        source_url="https://example.invalid/video",
        content={
            "media_references": [
                {
                    "kind": "video",
                    "media_type": "video/mp4",
                    "ref": "video-1",
                    "local_ref": "/synthetic/materialized/video.mp4",
                }
            ]
        },
    )
    before = build_modality_plan(record)
    assert before.has_video is True
    assert before.needs_frame_analysis is False

    record.content.frames.append(
        {
            "id": "frame-1",
            "timestamp_seconds": 3.0,
            "media_ref": "/synthetic/materialized/frame.jpg",
        }
    )
    after = build_modality_plan(record)
    assert after.needs_frame_analysis is True


def test_legacy_projection_is_adapter_not_source_evidence() -> None:
    provider = SequencedProvider(
        [
            MultimodalSummaryProposal(summary="Canonical descriptive result."),
            DiscourseProposal(),
        ]
    )
    record = CanonicalRecord(
        source_url="https://example.invalid/legacy-adapter",
        content={
            "text": "Text with an existing transcript.",
            "transcripts": [
                {
                    "id": "asr-1",
                    "text": "Transcript text",
                    "language": "fi",
                    "translated_text": "Translated transcript",
                }
            ],
        },
    )

    result = run_canonical_pipeline(
        record,
        provider=provider,
        context=context(),
        model="fake",
        project_profile="ai26",
    )
    legacy = result.legacy["multimodal_compatibility"]

    assert legacy["transcript"] == "Transcript text"
    assert legacy["transcript_language"] == "fi"
    assert legacy["translated_transcript"] == "Translated transcript"
    assert legacy["compatibility_status"] == "derived_from_phase1_canonical"
