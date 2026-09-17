"""Deterministic Hungary26 media-preprocessing policy.

The policy deliberately avoids the legacy v1 behaviour of aggressively fragmenting
videos merely to fit model context. It plans whole-video analysis for short media and
bounded overlapping segments for longer media; a private/media hook may refine candidate
boundaries with scene/keyframe detection while preserving this provenance contract.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaProfile:
    whole_video_max_seconds: float = 180.0
    min_segment_seconds: float = 20.0
    max_segment_seconds: float = 120.0
    overlap_seconds: float = 3.0


@dataclass(frozen=True)
class SegmentPlan:
    parent_media_id: str
    segment_id: str
    start_seconds: float
    end_seconds: float
    whole_video: bool


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plan_segments(parent_media_id: str, duration_seconds: float, profile: MediaProfile | None = None) -> list[SegmentPlan]:
    profile = profile or MediaProfile()
    if duration_seconds <= 0:
        return []
    if duration_seconds <= profile.whole_video_max_seconds:
        return [SegmentPlan(parent_media_id, f"{parent_media_id}:whole", 0.0, duration_seconds, True)]
    step = max(profile.min_segment_seconds, profile.max_segment_seconds - profile.overlap_seconds)
    plans: list[SegmentPlan] = []
    start = 0.0
    index = 1
    while start < duration_seconds:
        end = min(duration_seconds, start + profile.max_segment_seconds)
        if end - start < profile.min_segment_seconds and plans:
            previous = plans[-1]
            plans[-1] = SegmentPlan(previous.parent_media_id, previous.segment_id, previous.start_seconds, duration_seconds, False)
            break
        plans.append(SegmentPlan(parent_media_id, f"{parent_media_id}:seg-{index:04d}", start, end, False))
        if end >= duration_seconds:
            break
        start += step
        index += 1
    return plans


def segment_manifest(parent_media_id: str, duration_seconds: float, checksum: str, profile: MediaProfile | None = None) -> dict:
    plans = plan_segments(parent_media_id, duration_seconds, profile)
    return {
        "parent_media_id": parent_media_id,
        "source_checksum_sha256": checksum,
        "duration_seconds": duration_seconds,
        "status": "planned" if plans else "failed",
        "segments": [plan.__dict__ for plan in plans],
        "guardrails": {
            "whole_video_preferred_when_short": True,
            "preserve_parent_identity": True,
            "preserve_audio_continuity": True,
            "scene_keyframe_refinement_allowed": True,
            "silent_drop_forbidden": True,
        },
    }
