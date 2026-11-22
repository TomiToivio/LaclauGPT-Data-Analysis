"""Provider interfaces for optional ASR, OCR and vision implementations.

These protocols let callers depend on evidence contracts instead of
provider-specific media libraries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .evidence import OcrObservation, TranscriptSegment, VisualObservation


class AsrProvider(Protocol):
    """Convert media into transcript segments without prescribing a backend."""

    def transcribe(self, media_path: Path) -> list[TranscriptSegment]:
        """Extract transcript segments from a local media file."""
        ...


class OcrProvider(Protocol):
    """Extract visible text while retaining sampled-frame provenance."""

    def extract(
        self,
        frame_path: Path,
        *,
        frame_id: str,
        timestamp_seconds: float,
    ) -> list[OcrObservation]:
        """Return OCR observations linked to this frame and timestamp."""
        ...


class VisionProvider(Protocol):
    """Describe a sampled frame with an evidence-linked observation."""

    def describe(
        self,
        frame_path: Path,
        *,
        frame_id: str,
        timestamp_seconds: float,
    ) -> VisualObservation:
        """Return the visual observation for the specified frame."""
        ...
