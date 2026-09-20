from __future__ import annotations

import json
from pathlib import Path

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.canonical_pipeline import (
    DiscourseProposal,
    FrameProposal,
    MultimodalSummaryProposal,
    PipelineContext,
    run_canonical_pipeline,
    SummaryProposal,
)
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse


FIXTURE = Path(__file__).parent / "fixtures" / "ep24_media_sample.json"


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


def _fixture_record() -> CanonicalRecord:
    return CanonicalRecord.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _context(*, multimodal: bool) -> PipelineContext:
    return PipelineContext(
        project_config={
            "analysis_phase": 1,
            "analysis": {
                "multimodal": {"enabled": multimodal},
            },
        }
    )


def _summary() -> SummaryProposal:
    return SummaryProposal(summary="EP24 summary", narrative="Synthetic election clip summary.")


def test_ep24_frame_slice_is_disabled_by_default() -> None:
    provider = SequencedProvider([_summary(), DiscourseProposal()])
    record = _fixture_record()

    result = run_canonical_pipeline(
        record,
        provider=provider,
        context=PipelineContext(),
        project_profile="ep24",
        model="fake-model",
    )

    assert len(provider.requests) == 2
    assert not any(run.get("stage") == "frame" for run in result.analysis.model_runs)
    assert result.intermediate.stage_outputs["frame_analysis_skipped"][-1]["reason"] == (
        "multimodal_disabled"
    )


def test_ep24_frame_slice_can_be_enabled_independently_and_runs_before_summary() -> None:
    provider = SequencedProvider(
        [
            FrameProposal(description="Candidate at campaign event."),
            _summary(),
            DiscourseProposal(),
        ]
    )

    result = run_canonical_pipeline(
        _fixture_record(),
        provider=provider,
        context=_context(multimodal=True),
        project_profile="ep24",
        model="fake-model",
    )

    assert len(provider.requests) == 3
    assert result.intermediate.frame_analysis[0]["frame_id"] == "frame-001"
    assert "Required output JSON shape" in provider.requests[0].user
    assert provider.requests[0].images == ("tests/fixtures/ep24_frame_sample.ppm",)
    assert "frame-001" in provider.requests[0].user
    assert "Synthetic election clip summary" not in provider.requests[0].user
    assert result.human_readable.summary == "EP24 summary"
    visibility = result.intermediate.stage_outputs["multimodal_visibility"][-1]
    assert visibility["declared"] == "direct_image_pixels"
    assert visibility["attachments"][0]["frame_id"] == "frame-001"


def test_text_only_record_skips_frames_even_when_multimodal_enabled() -> None:
    record = _fixture_record()
    record.content.frames = []
    record.content.media_references = []
    provider = SequencedProvider([_summary(), DiscourseProposal()])

    result = run_canonical_pipeline(
        record,
        provider=provider,
        context=_context(multimodal=True),
        project_profile="ep24",
        model="fake-model",
    )

    assert len(provider.requests) == 2
    assert result.intermediate.stage_outputs["frame_analysis_skipped"][-1]["reason"] == (
        "text_only_or_no_extracted_frames"
    )


def test_ep24_frame_analysis_tolerates_missing_ocr_and_transcript_modalities() -> None:
    record = _fixture_record()
    assert record.content.ocr == []
    assert record.content.transcripts == []
    provider = SequencedProvider(
        [
            FrameProposal(description="Visual evidence only."),
            _summary(),
            DiscourseProposal(),
        ]
    )

    result = run_canonical_pipeline(
        record,
        provider=provider,
        context=_context(multimodal=True),
        project_profile="ep24",
        model="fake-model",
    )

    assert result.intermediate.frame_analysis
    assert result.human_readable.summary == "EP24 summary"


def test_ai26_with_frames_remains_text_first_without_explicit_multimodal_activation() -> None:
    # No OCR/Whisper/download hook is passed here. The presence of an already
    # extracted frame must not itself activate multimodal analysis.
    provider = SequencedProvider([
        MultimodalSummaryProposal(summary="Text-first summary"),
        DiscourseProposal(),
    ])

    result = run_canonical_pipeline(
        _fixture_record(),
        provider=provider,
        context=PipelineContext(),
        project_profile="ai26",
        model="fake-model",
    )

    assert len(provider.requests) == 2
    assert not any(run.get("stage") == "multimodal_frame" for run in result.analysis.model_runs)
    assert result.intermediate.stage_outputs["frame_analysis_skipped"][-1]["reason"] == (
        "multimodal_disabled"
    )
