"""Capability-driven modality routing for the Phase 1 canonical pipeline.

The router is intentionally cheap and dependency-free.  It runs after generic
preprocessing has had a chance to materialize media and records what can actually
be processed.  References and historical derivatives do not become direct media
evidence merely because they exist in the record.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .canonical import CanonicalRecord, FrameReference, MediaReference

CoverageState = Literal[
    "processed", "partial", "not_provided", "not_processed", "unsupported", "failed"
]

_IMAGE_HINTS = ("image/", "photo", "image", "picture", "screenshot", "thumbnail")
_VIDEO_HINTS = ("video/", "video", "movie", "clip")
_AUDIO_HINTS = ("audio/", "audio", "sound", "podcast")


def _media_family(media: MediaReference) -> str:
    value = " ".join(
        str(part or "").casefold()
        for part in (media.kind, media.media_type, media.metadata.get("mime_type"))
    )
    if any(hint in value for hint in _VIDEO_HINTS):
        return "video"
    if any(hint in value for hint in _IMAGE_HINTS):
        return "image"
    if any(hint in value for hint in _AUDIO_HINTS):
        return "audio"
    return "other"


def _materialized(media: MediaReference) -> bool:
    """Return whether a source media reference has a local/materialized representation.

    File existence is verified by the media-specific adapter before bytes are
    attached to a model request.  At routing time, local_ref is the canonical
    signal that the storage/preprocessing layer claims materialization.
    """
    return bool((media.local_ref or "").strip())


@dataclass(frozen=True)
class ModalityPlan:
    has_text: bool
    has_image: bool
    has_video: bool
    has_audio: bool
    has_transcript: bool
    has_ocr: bool
    has_frames: bool
    declared_images: int
    declared_videos: int
    declared_audio: int
    materialized_images: int
    materialized_videos: int
    materialized_audio: int

    @property
    def has_visual_media(self) -> bool:
        return self.has_image or self.has_video or self.has_frames

    @property
    def needs_frame_analysis(self) -> bool:
        # Still images may be represented by a canonical frame; videos require
        # extracted frames before frame analysis can run.
        return self.has_frames and self.has_visual_media

    @property
    def needs_asr(self) -> bool:
        return self.has_audio or self.has_video

    @property
    def is_text_only(self) -> bool:
        return self.has_text and not (
            self.has_visual_media or self.has_audio or self.has_transcript or self.has_ocr
        )

    def audit(self) -> dict[str, object]:
        return {
            "has_text": self.has_text,
            "has_image": self.has_image,
            "has_video": self.has_video,
            "has_audio": self.has_audio,
            "has_transcript": self.has_transcript,
            "has_ocr": self.has_ocr,
            "has_frames": self.has_frames,
            "has_visual_media": self.has_visual_media,
            "needs_frame_analysis": self.needs_frame_analysis,
            "needs_asr": self.needs_asr,
            "is_text_only": self.is_text_only,
            "declared_media": {
                "image": self.declared_images,
                "video": self.declared_videos,
                "audio": self.declared_audio,
            },
            "materialized_media": {
                "image": self.materialized_images,
                "video": self.materialized_videos,
                "audio": self.materialized_audio,
            },
        }


def ensure_still_image_frames(record: CanonicalRecord) -> CanonicalRecord:
    """Represent each materialized still image as a timestamp-zero visual unit.

    This gives still images the same audited frame-analysis path as extracted
    video frames without pretending they came from video decoding.
    """
    existing_refs = {str(frame.media_ref) for frame in record.content.frames if frame.media_ref}
    next_index = len(record.content.frames) + 1
    for media in record.content.media_references:
        if _media_family(media) != "image" or not _materialized(media):
            continue
        media_key = str(media.ref or media.local_ref or "")
        if not media_key or media_key in existing_refs:
            continue
        record.content.frames.append(
            FrameReference(
                id=f"image-{next_index:03d}",
                timestamp_seconds=0.0,
                media_ref=media.ref or media.local_ref,
                description="Materialized still image",
            )
        )
        existing_refs.add(media_key)
        next_index += 1
    return record


def build_modality_plan(record: CanonicalRecord) -> ModalityPlan:
    images = videos = audio = 0
    materialized_images = materialized_videos = materialized_audio = 0

    for media in record.content.media_references:
        family = _media_family(media)
        if family == "image":
            images += 1
            materialized_images += int(_materialized(media))
        elif family == "video":
            videos += 1
            materialized_videos += int(_materialized(media))
        elif family == "audio":
            audio += 1
            materialized_audio += int(_materialized(media))

    # Direct visual processing is allowed only for materialized source media or
    # already-extracted canonical frames. A remote URL/object key alone is not
    # visual evidence.
    has_image = materialized_images > 0
    has_video = materialized_videos > 0
    has_audio = materialized_audio > 0

    return ModalityPlan(
        has_text=bool((record.content.text or "").strip()),
        has_image=has_image,
        has_video=has_video,
        has_audio=has_audio,
        has_transcript=bool(record.content.transcripts or record.intermediate.asr),
        has_ocr=bool(record.content.ocr or record.intermediate.ocr),
        has_frames=bool(record.content.frames or record.intermediate.frames),
        declared_images=images,
        declared_videos=videos,
        declared_audio=audio,
        materialized_images=materialized_images,
        materialized_videos=materialized_videos,
        materialized_audio=materialized_audio,
    )


def legacy_multimodal_projection(record: CanonicalRecord) -> dict[str, object]:
    """Project canonical Phase 1 data into the useful legacy EP24 surface.

    This is an adapter only.  Canonical source/derived representations remain
    authoritative and provenance-distinct.
    """
    transcripts = list(record.content.transcripts)
    primary = transcripts[0] if transcripts else None
    frame_files = []
    for frame in record.content.frames:
        if frame.media_ref:
            frame_files.append(frame.media_ref)

    ocr_values = [item.text for item in record.content.ocr]
    if not ocr_values:
        ocr_values = [str(item.get("text", "")) for item in record.intermediate.ocr if item.get("text")]

    return {
        "frame_files": frame_files,
        "frame_analyses": list(record.intermediate.frame_analysis),
        "ocr": ocr_values,
        "transcript": primary.text if primary else "",
        "transcript_language": primary.language if primary else None,
        "translated_transcript": primary.translated_text if primary else None,
        "multimodal_summary": record.human_readable.summary,
        "compatibility_status": "derived_from_phase1_canonical",
    }
