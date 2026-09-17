"""Human review and provisional-AI exchange helpers for DATS workflows."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .interoperability import Annotation, ExternalRef, HumanReview, Producer


def provisional_ai_annotation(
    *,
    annotation_id: str,
    source_url: str,
    evidence_id: str,
    code_id: str,
    model_id: str,
    model_version: str | None,
    confidence: float | None,
    prompt_id: str | None = None,
    run_id: str | None = None,
) -> Annotation:
    """Create an annotation proposal that cannot masquerade as human coding."""
    return Annotation(
        annotation_id=annotation_id,
        source_url=source_url,
        evidence_id=evidence_id,
        code_id=code_id,
        producer=Producer(type="model", id=model_id, version=model_version),
        review_status="PROVISIONAL",
        confidence=confidence,
        metadata={"prompt_id": prompt_id, "run_id": run_id, "human_verified": False},
    )


def import_dats_human_correction(payload: dict[str, Any]) -> HumanReview:
    """Normalize a DATS correction/review event into an explicit HumanReview."""
    if not payload.get("reviewer"):
        raise ValueError("DATS human correction requires reviewer identity")
    if not payload.get("target_id"):
        raise ValueError("DATS human correction requires target_id")
    reviewed_at = payload.get("reviewed_at")
    if not reviewed_at:
        raise ValueError("DATS human correction requires reviewed_at")
    return HumanReview(
        review_id=str(payload.get("review_id") or f"dats-review:{payload['target_id']}"),
        target_id=str(payload["target_id"]),
        reviewer=str(payload["reviewer"]),
        decision=payload.get("decision", "REVISED"),
        reviewed_at=datetime.fromisoformat(str(reviewed_at).replace("Z", "+00:00")),
        note=payload.get("note"),
        corrections=payload.get("corrections", {}),
        external_ids=[
            ExternalRef(system="dats", id=str(payload.get("id") or payload.get("review_id") or ""))
        ]
        if payload.get("id") or payload.get("review_id")
        else [],
    )
