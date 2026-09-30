"""Issue #303 — the six modality-routing cases the refactor must guarantee.

The pipeline is multimodal *by default*: routing is decided by what the record
actually carries, not by a flag a researcher has to discover. These tests pin that
contract for the six record shapes the issue enumerates, and they assert on the
ROUTING DECISION (which stages run) rather than on model output — routing is the
part that was previously implicit and therefore the part that could silently
regress.

Cases covered (issue #303 requirement 6):
1. text + metadata only                      -> text path, no dummy media needed
2. image/frame + text + metadata             -> visual path taken automatically
3. video-derived frames + transcript + text  -> visual path, transcript available
4. media present but one derived modality missing -> must NOT fail the record
5. representative legacy EP24-style record   -> still routed
6. current AI26-style text record            -> text path
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from laclaugpt_data_analysis.canonical import (  # noqa: E402
    CanonicalRecord,
    FrameReference,
    MediaReference,
)
from laclaugpt_data_analysis.modality_routing import (  # noqa: E402
    build_modality_plan,
    ensure_still_image_frames,
)


def _plan(record: CanonicalRecord):
    """Run the routing pipeline exactly as the runner does, in order."""
    ensure_still_image_frames(record)
    return build_modality_plan(record)


# ---------------------------------------------------------------------------
# Case 1 — text + metadata only
# ---------------------------------------------------------------------------


def test_case1_text_and_metadata_only_routes_to_text_path() -> None:
    """A text-only record needs no media fields and must be marked text-only."""
    record = CanonicalRecord(
        source_url="https://example.invalid/text",
        content={"text": "A post about artificial intelligence policy."},
    )
    plan = _plan(record)

    assert plan.has_text is True
    assert plan.is_text_only is True, "text+metadata alone must be the text path"
    assert plan.needs_frame_analysis is False, "no media -> no frame stage"
    assert plan.declared_images == 0 and plan.declared_videos == 0


# ---------------------------------------------------------------------------
# Case 2 — image/frame + text + metadata
# ---------------------------------------------------------------------------


def test_case2_materialized_image_routes_visual_without_a_flag() -> None:
    """A materialised still image reaches the visual path with no opt-in flag."""
    record = CanonicalRecord(
        source_url="https://example.invalid/image",
        content={
            "text": "Protest outside parliament.",
            "media_references": [
                MediaReference(
                    kind="image",
                    media_type="image/jpeg",
                    ref="media/001.jpg",
                    local_ref="/tmp/media/001.jpg",
                )
            ],
        },
    )
    plan = _plan(record)

    assert plan.materialized_images == 1, "local_ref is the materialisation signal"
    assert plan.needs_frame_analysis is True, "materialised image must reach frame analysis"
    assert plan.has_visual_media is True
    # The still image became a canonical frame, giving it the audited path.
    assert plan.has_frames is True


def test_case2b_declared_but_unmaterialized_image_does_not_fake_visual_evidence() -> None:
    """A remote URL alone is not visual evidence; routing must not pretend it is."""
    record = CanonicalRecord(
        source_url="https://example.invalid/remote-image",
        content={
            "text": "Caption only.",
            "media_references": [
                MediaReference(kind="image", media_type="image/jpeg", url="https://cdn.invalid/x.jpg")
            ],
        },
    )
    plan = _plan(record)

    assert plan.declared_images == 1
    assert plan.materialized_images == 0
    assert plan.needs_frame_analysis is False, (
        "an unmaterialised remote image must not be treated as analysable visual evidence"
    )


# ---------------------------------------------------------------------------
# Case 3 — video-derived frames + transcript + text
# ---------------------------------------------------------------------------


def test_case3_video_frames_and_transcript_route_visual() -> None:
    """Extracted frames plus a transcript take the visual path and carry the ASR."""
    record = CanonicalRecord(
        source_url="https://example.invalid/video",
        content={
            "text": "Short caption.",
            "frames": [
                FrameReference(id="f-001", timestamp_seconds=0.0, media_ref="frames/001.jpg"),
                FrameReference(id="f-002", timestamp_seconds=2.5, media_ref="frames/002.jpg"),
            ],
            "transcripts": [
                {"id": "t1", "text": "spoken words", "language": "en"},
            ],
            "media_references": [
                MediaReference(
                    kind="video",
                    media_type="video/mp4",
                    ref="media/v.mp4",
                    local_ref="/tmp/media/v.mp4",
                )
            ],
        },
    )
    plan = _plan(record)

    assert plan.has_video is True
    assert plan.has_frames is True
    assert plan.has_transcript is True
    assert plan.needs_frame_analysis is True, "video with frames must analyse frames"
    assert plan.needs_asr is True, "video implies audio that may need transcription"


# ---------------------------------------------------------------------------
# Case 4 — media present but one derived modality missing
# ---------------------------------------------------------------------------


def test_case4_missing_derived_modality_does_not_fail_the_record() -> None:
    """Audio present but ASR produced nothing: routing must degrade, not fail.

    The record still has usable text, so the analysis proceeds on what exists.
    A missing derived modality is recorded as absent, never raised.
    """
    record = CanonicalRecord(
        source_url="https://example.invalid/partial",
        content={
            "text": "Text survives even when ASR failed.",
            "media_references": [
                MediaReference(
                    kind="audio",
                    media_type="audio/mpeg",
                    ref="media/a.mp3",
                    local_ref="/tmp/media/a.mp3",
                )
            ],
        },
    )
    plan = _plan(record)  # must not raise

    assert plan.materialized_audio == 1
    assert plan.has_audio is True
    assert plan.has_transcript is False, "ASR produced nothing; recorded as absent"
    assert plan.has_text is True, "the text path remains available"
    assert plan.is_text_only is False, "audio presence means it is not text-only"
    assert plan.needs_frame_analysis is False, "no visual media -> no frame stage"


# ---------------------------------------------------------------------------
# Case 5 — representative legacy EP24-style record
# ---------------------------------------------------------------------------


def test_case5_legacy_ep24_style_record_still_routes() -> None:
    """A legacy-shaped record (extra fields, EP24 vocabulary) routes normally."""
    record = CanonicalRecord(
        source_url="https://example.invalid/ep24",
        content={
            "text": "EP24 campaign post.",
            "media_references": [
                MediaReference(
                    kind="photo",  # legacy wording for an image
                    media_type="image/png",
                    ref="legacy/photo.png",
                    local_ref="/tmp/legacy/photo.png",
                )
            ],
        },
        legacy={"frame_files": ["legacy/f0.jpg"], "transcript": "legacy transcript"},
    )
    plan = _plan(record)

    assert plan.materialized_images == 1, "'photo' must still be recognised as an image"
    assert plan.needs_frame_analysis is True
    # Legacy payload is preserved rather than re-interpreted as source truth.
    assert record.legacy["frame_files"] == ["legacy/f0.jpg"]


# ---------------------------------------------------------------------------
# Case 6 — current AI26-style text record
# ---------------------------------------------------------------------------


def test_case6_ai26_text_record_takes_text_path() -> None:
    """A present-day AI26 text record with metadata routes to the text path."""
    record = CanonicalRecord(
        source_url="https://example.invalid/ai26",
        content={
            "text": "An AI company announced a new model.",
            "media_references": [],
        },
        source={"raw_metadata": {"platform": "rss", "published_at": "2026-09-01"}},
    )
    plan = _plan(record)

    assert plan.has_text is True
    assert plan.is_text_only is True
    assert plan.needs_frame_analysis is False


# ---------------------------------------------------------------------------
# Cross-cutting: mixed-modality datasets work record-by-record
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "has_image,expected_visual",
    [(True, True), (False, False)],
)
def test_mixed_dataset_routes_per_record(has_image: bool, expected_visual: bool) -> None:
    """One project can hold text-only and visual records; routing is per record."""
    content: dict = {"text": "item"}
    if has_image:
        content["media_references"] = [
            MediaReference(kind="image", media_type="image/jpeg", local_ref="/tmp/i.jpg")
        ]
    record = CanonicalRecord(source_url="https://example.invalid/mix", content=content)
    plan = _plan(record)
    assert plan.needs_frame_analysis is expected_visual
