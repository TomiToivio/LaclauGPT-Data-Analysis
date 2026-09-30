"""Step 2: inspect visual material when the record actually contains it.

The routing rule is deliberately human-readable:

* materialized still images become timestamp-zero canonical frames;
* extracted video frames are used when present;
* text-only records skip visual analysis;
* missing media never requires dummy placeholders.

The heavy model/provider details remain in shared infrastructure.
"""
from __future__ import annotations

from datetime import UTC, datetime

from ..canonical import CanonicalRecord
from ..canonical_pipeline import PipelineContext, _append_stage, analyze_frames
from ..codebooks import CodebookEntry
from ..modality_routing import ModalityPlan, build_modality_plan, ensure_still_image_frames


def plan_modalities(record: CanonicalRecord) -> ModalityPlan:
    """Normalize still images and return an auditable record-by-record media plan."""
    ensure_still_image_frames(record)
    return build_modality_plan(record)


def run_frame_analysis(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext,
    codebook_entries: list[CodebookEntry],
    model: str,
    prompt_version: str,
    project_profile: str,
    allow_cloud_fallback: bool | None,
    plan: ModalityPlan | None = None,
) -> CanonicalRecord:
    """Analyze visual frames when available; otherwise document why the step skipped."""
    modality_plan = plan or plan_modalities(record)
    _append_stage(
        record,
        "modality_plan",
        {"created_at": datetime.now(UTC).isoformat(), **modality_plan.audit()},
    )

    if not modality_plan.needs_frame_analysis:
        _append_stage(
            record,
            "frame_analysis_skipped",
            {
                "created_at": datetime.now(UTC).isoformat(),
                "reason": "no_materialized_image_or_video_frames",
                "modality_plan": modality_plan.audit(),
            },
        )
        return record

    # The wrapper that attaches image bytes to model requests is imported only
    # for records that truly have processable visual material.
    from ..llm.multimodal import FrameAwareProvider

    frame_provider = FrameAwareProvider(
        provider,
        record.content.frames,
        record.content.media_references,
    )
    analyze_frames(
        record,
        provider=frame_provider,
        context=context,
        codebook_entries=codebook_entries,
        model=model,
        prompt_version=prompt_version,
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )
    _append_stage(record, "multimodal_visibility", frame_provider.audit())
    return record
