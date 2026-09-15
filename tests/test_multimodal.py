from __future__ import annotations

import json

from laclaugpt_data_analysis.exporters import write_multimodal_csv, write_multimodal_jsonl
from laclaugpt_data_analysis.multimodal.evidence import (
    MultimodalEvidenceBundle,
    OcrObservation,
    TranscriptSegment,
    VisualObservation,
)
from laclaugpt_data_analysis.multimodal.frames import sample_timestamps
from laclaugpt_data_analysis.multimodal.fusion import build_evidence_text, researcher_summary


def synthetic_bundle() -> MultimodalEvidenceBundle:
    return MultimodalEvidenceBundle(
        document_id="synthetic-video-1",
        source_uri="file:///synthetic/video.mp4",
        transcript=[
            TranscriptSegment(
                segment_id="asr-1",
                start_seconds=0,
                end_seconds=4.5,
                text="Synthetic campaign statement.",
                language="en",
            )
        ],
        ocr=[
            OcrObservation(
                observation_id="ocr-1",
                frame_id="frame-0",
                timestamp_seconds=0,
                text="VOTE EXAMPLE",
            )
        ],
        visuals=[
            VisualObservation(
                observation_id="vision-1",
                frame_id="frame-0",
                timestamp_seconds=0,
                description="A synthetic speaker at a lectern.",
            )
        ],
        metadata={"platform": "synthetic", "duration_seconds": 12},
    )


def test_frame_sampling_generalizes_legacy_policy() -> None:
    assert sample_timestamps(181) == [0.0, 30.0, 60.0, 90.0, 120.0, 150.0]
    assert sample_timestamps(1) == [0.0]
    assert sample_timestamps(0) == []


def test_fusion_preserves_evidence_ids_and_timestamps() -> None:
    text = build_evidence_text(synthetic_bundle())
    assert "asr-1" in text
    assert "ocr-1" in text
    assert "vision-1" in text
    assert "0.0s" in text


def test_missing_modalities_are_explicit() -> None:
    bundle = MultimodalEvidenceBundle(
        document_id="no-audio",
        missing_modalities=["audio", "ocr"],
        metadata={"duration_seconds": 5},
    )
    assert bundle.has_evidence
    summary = researcher_summary(bundle)
    assert "Unavailable: audio, ocr." in summary


def test_serialization_and_exports_round_trip(tmp_path) -> None:
    bundle = synthetic_bundle()
    jsonl = tmp_path / "results.jsonl"
    csv_file = tmp_path / "results.csv"
    write_multimodal_jsonl([bundle], jsonl)
    write_multimodal_csv([bundle], csv_file)

    payload = json.loads(jsonl.read_text(encoding="utf-8").strip())
    restored = MultimodalEvidenceBundle.model_validate(payload)
    assert restored == bundle
    assert "synthetic-video-1" in csv_file.read_text(encoding="utf-8")


def test_researcher_summary_is_human_readable_but_not_canonical() -> None:
    summary = researcher_summary(synthetic_bundle())
    assert summary.startswith("# Multimodal evidence: synthetic-video-1")
    assert "Synthetic campaign statement." in summary
    assert "VOTE EXAMPLE" in summary
