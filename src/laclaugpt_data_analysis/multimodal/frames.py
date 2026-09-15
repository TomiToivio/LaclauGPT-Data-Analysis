"""Frame sampling policy independent of OpenCV or any media backend."""
from __future__ import annotations


def sample_timestamps(
    duration_seconds: float,
    *,
    interval_seconds: float = 30.0,
    max_frames: int = 6,
) -> list[float]:
    """Return deterministic frame timestamps for a media item.

    This generalizes the EP2024 policy of sampling up to six frames at
    30-second intervals while handling short and missing media safely.
    """
    if duration_seconds <= 0 or max_frames <= 0:
        return []
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    timestamps: list[float] = []
    current = 0.0
    while current < duration_seconds and len(timestamps) < max_frames:
        timestamps.append(current)
        current += interval_seconds
    return timestamps
