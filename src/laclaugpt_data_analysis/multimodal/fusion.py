"""Deterministic multimodal evidence fusion and researcher-readable rendering."""
from __future__ import annotations

from .evidence import MultimodalEvidenceBundle


def build_evidence_text(bundle: MultimodalEvidenceBundle) -> str:
    """Render canonical evidence for an LLM/provider without losing source links."""
    parts: list[str] = [f"Document: {bundle.document_id}"]
    if bundle.metadata:
        metadata = "; ".join(f"{key}={bundle.metadata[key]}" for key in sorted(bundle.metadata))
        parts.append(f"Metadata: {metadata}")

    for segment in sorted(bundle.transcript, key=lambda item: (item.start_seconds, item.segment_id)):
        parts.append(
            f"Transcript [{segment.start_seconds:.1f}-{segment.end_seconds:.1f}s] "
            f"({segment.segment_id}): {segment.text}"
        )
    for observation in sorted(bundle.ocr, key=lambda item: (item.timestamp_seconds, item.observation_id)):
        parts.append(
            f"OCR [{observation.timestamp_seconds:.1f}s] "
            f"({observation.observation_id}, frame={observation.frame_id}): {observation.text}"
        )
    for observation in sorted(
        bundle.visuals, key=lambda item: (item.timestamp_seconds, item.observation_id)
    ):
        parts.append(
            f"Visual [{observation.timestamp_seconds:.1f}s] "
            f"({observation.observation_id}, frame={observation.frame_id}): "
            f"{observation.description}"
        )
    if bundle.missing_modalities:
        parts.append("Missing modalities: " + ", ".join(sorted(set(bundle.missing_modalities))))
    return "\n".join(parts)


def researcher_summary(bundle: MultimodalEvidenceBundle) -> str:
    """Produce a deterministic human-readable evidence summary.

    This is intentionally descriptive. Interpretive claims belong to the canonical
    analysis/codebook pipeline and should cite the evidence identifiers rendered here.
    """
    lines = [f"# Multimodal evidence: {bundle.document_id}"]
    if bundle.source_uri:
        lines.append(f"Source: {bundle.source_uri}")
    lines.append(
        f"Evidence: {len(bundle.transcript)} transcript segment(s), "
        f"{len(bundle.ocr)} OCR observation(s), {len(bundle.visuals)} visual observation(s)."
    )
    if bundle.missing_modalities:
        lines.append("Unavailable: " + ", ".join(sorted(set(bundle.missing_modalities))) + ".")
    lines.append("")
    lines.append(build_evidence_text(bundle))
    return "\n".join(lines)
