"""Provider contracts for optional ASR, OCR, and vision implementations."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .evidence import OcrObservation, TranscriptSegment, VisualObservation


class AsrProvider(Protocol):
    def transcribe(self, media_path: Path) -> list[TranscriptSegment]: ...


class OcrProvider(Protocol):
    def extract(self, frame_path: Path, *, frame_id: str, timestamp_seconds: float) -> list[OcrObservation]: ...


class VisionProvider(Protocol):
    def describe(self, frame_path: Path, *, frame_id: str, timestamp_seconds: float) -> VisualObservation: ...
