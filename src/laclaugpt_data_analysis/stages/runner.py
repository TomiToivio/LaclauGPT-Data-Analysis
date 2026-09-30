"""Stage 5 — runner: the thin orchestration that sequences the pipeline.

This is the file to read first. It says, in order, what happens to one post:

    source record
      -> preprocess            (extract ASR/OCR/frames/translations)
      -> frame analysis        (only when usable visual media exists)
      -> summary               (descriptive first pass)
      -> laclau               (Laclau/Mouffe discourse analysis)
      -> postprocess           (write the canonical analysis record)
      -> discourse graph       (project for export/dashboard)

Everything here is sequencing, routing, and error handling. It deliberately
contains no research logic: each step lives in its own module next to this one,
so a researcher can read the science without reading the plumbing.

Multimodal-by-default routing
-----------------------------
The default is decided by the record, not by a flag:

* if the record has materialised media or extracted frames, the frame stage runs
  automatically and the summary synthesises across all available modalities
  (text, caption, transcript, visible text, frame descriptions);
* if there is no usable media, the text path runs on post text plus metadata, and
  no dummy media fields are required;
* a missing *derived* modality (e.g. audio present but ASR failed) never fails the
  record — the modality plan records what was available and the analysis proceeds
  with what exists.

Project configuration may still switch expensive modality work off explicitly,
but a researcher does not have to discover and flip a flag merely because media
exists.
"""
from __future__ import annotations

from datetime import UTC, datetime

from ..canonical import CanonicalRecord
from ..codebooks import CodebookEntry
from ..modality_routing import (
    build_modality_plan,
    ensure_still_image_frames,
    legacy_multimodal_projection,
)
from .evidence import evidence_ids as _evidence_ids_impl
from .frame import analyze_frames
from .graph import build_discourse_graph
from .laclau import discourse_analysis
from .postprocess import postprocess_record
from .preprocess import preprocess_record
from .proposals import DiscourseProposal
from .shared import (
    GraphSink,
    PipelineContext,
    Preprocessor,
    VectorSink,
    append_stage,
    enabled,
    now_iso,
    validate_project_analysis_config,
)
from .summary import summarize_record


def run_canonical_pipeline(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext | None = None,
    codebook_entries: list[CodebookEntry] | None = None,
    preprocessor: Preprocessor | None = None,
    graph_sink: GraphSink | None = None,
    vector_sink: VectorSink | None = None,
    model: str = "auto",
    project_profile: str = "generic",
    prompt_version: str = "canonical-pipeline-v1",
    allow_cloud_fallback: bool | None = None,
) -> CanonicalRecord:
    """Run the complete default Phase 1 pipeline on one canonical record."""
    ctx = context or PipelineContext()
    if project_profile.casefold() == "ai26":
        validate_project_analysis_config(ctx)
    entries = codebook_entries or []
    record.analysis.started_at = record.analysis.started_at or datetime.now(UTC)

    # 1. Enrich: derived inputs (ASR, OCR, frames, translations).
    preprocess_record(record, preprocessor=preprocessor)

    # 2. Decide modality routing from what the record actually carries. Frames are
    #    materialised first so a video-only record can still reach the visual path.
    ensure_still_image_frames(record)
    plan = build_modality_plan(record)
    append_stage(record, "modality_plan", {"created_at": now_iso(), **plan.audit()})

    if plan.needs_frame_analysis:
        # Import the image-capable adapter lazily. Text/audio-only records never
        # need multimodal dependencies or a vision-capable provider wrapper.
        from ..llm.multimodal import FrameAwareProvider

        frame_provider = FrameAwareProvider(
            provider,
            record.content.frames,
            record.content.media_references,
        )
        analyze_frames(
            record,
            provider=frame_provider,
            context=ctx,
            codebook_entries=entries,
            model=model,
            prompt_version=f"{prompt_version}:frame",
            project_profile=project_profile,
            allow_cloud_fallback=allow_cloud_fallback,
        )
        append_stage(record, "multimodal_visibility", frame_provider.audit())
    else:
        append_stage(
            record,
            "frame_analysis_skipped",
            {
                "created_at": now_iso(),
                "reason": "no_materialized_image_or_video_frames",
                "modality_plan": plan.audit(),
            },
        )

    # 3. Descriptive pass over the whole item, then 4. the theory stage.
    summary = summarize_record(
        record,
        provider=provider,
        context=ctx,
        codebook_entries=entries,
        model=model,
        prompt_version=f"{prompt_version}:summary",
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )
    discourse = (
        discourse_analysis(
            record,
            provider=provider,
            context=ctx,
            codebook_entries=entries,
            model=model,
            prompt_version=f"{prompt_version}:discourse",
            project_profile=project_profile,
            allow_cloud_fallback=allow_cloud_fallback,
        )
        if enabled(ctx, "laclau") or project_profile.casefold() != "ai26"
        else DiscourseProposal()
    )

    # 5. Write the canonical analysis record.
    postprocess_record(record, summary, discourse, ctx)
    record.legacy["multimodal_compatibility"] = legacy_multimodal_projection(record)

    # Phase 2 / experimental methods remain explicit opt-ins and never enter the
    # Phase 1 default path. They run only after the five canonical Phase 1 stages.
    if enabled(ctx, "critical_ai", default=False):
        from ..critical_ai import run_optional_critical_ai

        run_optional_critical_ai(
            record,
            provider=provider,
            context=ctx,
            codebook_entries=entries,
            model=model,
            allow_cloud_fallback=allow_cloud_fallback,
        )
    elif enabled(ctx, "dna_statement_coding", default=False):
        from ..dna_statement_coding import run_optional_dna_statement_coding

        run_optional_dna_statement_coding(
            record,
            provider=provider,
            context=ctx,
            codebook_entries=entries,
            model=model,
            allow_cloud_fallback=allow_cloud_fallback,
        )

    # 6. Project and persist.
    graph = build_discourse_graph(record)
    append_stage(record, "discourse_graph", graph)
    if graph_sink:
        graph_sink.write_graph(record.source_url, graph)
    if vector_sink:
        vector_sink.upsert(
            record.source_url,
            record.human_readable.markdown or record.content.text,
            {"source_url": record.source_url, "project_profile": project_profile},
        )
    return record


# Re-exported so callers of the old monolith keep one import path, and so the
# facade's `_evidence_ids` IS this function rather than a wrapper around it.
evidence_ids = _evidence_ids_impl
