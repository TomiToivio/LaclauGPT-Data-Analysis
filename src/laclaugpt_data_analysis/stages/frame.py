"""Stage 2a — frame: per-image / per-frame multimodal evidence analysis.

Purpose
-------
When a record carries usable visual material (materialised images, or frames
extracted from video), describe each frame as *evidence*: what is visible, what
text appears in it, what is happening. Run once per frame.

Why this stage is separate from the summary
-------------------------------------------
A frame is analysed on its own, then the summary synthesises across frames and
text. Collapsing the two would let a single image's interpretation silently
become the item-level description, and would make a per-frame retry impossible.

This is the stage that makes the pipeline multimodal by default: it is entered
whenever the modality plan says frames are available. It is *not* an opt-in flag
a researcher has to discover — see `stages/runner.py` for the routing.

Scientific boundary
-------------------
Descriptive only. `assert_preanalysis_boundary` enforces this: the frame prompt
must not perform theory-specific classification (ideology, populism, discourse
formations). That work belongs to the discourse stage, and keeping it out here
prevents early description from hardening into a finding.

Inputs
------
* `record` with `record.content.frames` populated;
* `provider` — a frame-capable model wrapper (the runner supplies one that can
  actually see the images);
* `context`, `codebook_entries`, `model`, `prompt_version`, `project_profile`.

Outputs
-------
* `record.intermediate.frame_analysis` — one entry per frame, carrying the
  proposal, the prompt provenance and the model-run metadata;
* `record.analysis.model_runs` — appended per frame;
* stage output `frame_analysis_skipped` when there was nothing visual to analyse.
"""
from __future__ import annotations

from datetime import UTC, datetime

from ..canonical import CanonicalRecord
from ..codebooks import CodebookEntry
from ..llm.structured_output import chat_structured
from ..prompt_library import load_prompt, prompt_provenance
from ..social_semiotic import MultimodalFrameProposal, assert_preanalysis_boundary
from .prompt_map import phase1_preanalysis_prompt_ids
from .shared import PipelineContext, append_stage, envelope_for_stage, model_run_metadata


def analyze_frames(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext,
    codebook_entries: list[CodebookEntry],
    model: str,
    prompt_version: str,
    project_profile: str,
    allow_cloud_fallback: bool | None,
) -> CanonicalRecord:
    """Describe every frame in the record; no-op when there are none."""
    if not record.content.frames:
        append_stage(
            record,
            "frame_analysis_skipped",
            {
                "created_at": datetime.now(UTC).isoformat(),
                "reason": "text_only_or_no_extracted_frames",
            },
        )
        return record

    # Phase 1 is capability-driven: the presence of canonical visual units is
    # the activation gate. Text-only records have already returned above.
    system_id, task_id = phase1_preanalysis_prompt_ids("frame")
    system_resource = load_prompt(system_id, version="v2")
    task_resource = load_prompt(task_id, version="v2")

    for frame in record.content.frames:
        rendered_task = task_resource.render(
            frame_id=frame.id,
            timestamp_seconds=frame.timestamp_seconds,
            project_note=f"{project_profile.upper()} source context only; remain descriptive.",
        )
        envelope = envelope_for_stage(
            record,
            context,
            task=rendered_task.text,
            codebook_entries=codebook_entries,
            prompt_version=prompt_version,
        )
        proposal, response = chat_structured(
            provider,
            MultimodalFrameProposal,
            model=model,
            system_prompt=system_resource.text,
            user_prompt=envelope.render(),
            allow_cloud_fallback=allow_cloud_fallback,
        )
        assert_preanalysis_boundary(proposal.model_dump(mode="json"))

        prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
        run_meta = model_run_metadata(
            context,
            response,
            prompt_meta,
            prompt_version=prompt_version,
            stage="social_semiotic_frame",
        )
        record.intermediate.frame_analysis.append(
            {
                "frame_id": frame.id,
                "timestamp_seconds": frame.timestamp_seconds,
                "analysis": proposal.model_dump(mode="json"),
                "prompt_version": prompt_version,
                **prompt_meta,
                "context_provenance": envelope.provenance_snapshot(),
                "model_run": run_meta,
            }
        )
        record.analysis.model_runs.append(run_meta)
    return record
