"""Reusable multimodal analysis primitives."""

from .evidence import (
    MultimodalEvidenceBundle,
    OcrObservation,
    TranscriptSegment,
    VisualObservation,
)
from .fusion import build_evidence_text, researcher_summary

__all__ = [
    "MultimodalEvidenceBundle",
    "OcrObservation",
    "TranscriptSegment",
    "VisualObservation",
    "build_evidence_text",
    "researcher_summary",
]
