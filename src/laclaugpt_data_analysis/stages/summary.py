"""Stage 2b — summary: the descriptive first pass over the whole item.

Purpose
-------
Produce the item-level description that everything later depends on: what the
post says, what it appears to be about, which entities and topics it names, what
claims, demands and grievances it contains, and what futures it imagines. This
pass synthesises across the modalities available (text, caption, transcript,
visible text, frame descriptions).

Why it exists as its own step
-----------------------------
The theory stage must be able to rely on a description it did not itself write.
Separating them means:

* the description can be reviewed and corrected by a researcher independently of
  the interpretation;
* a theory-stage change cannot silently alter the description;
* a failed or truncated summary is visibly the summary's problem.

Scientific boundary
-------------------
Descriptive, not interpretive. This stage may name what is present; it may not
classify ideology, populism or discourse formations. `assert_preanalysis_boundary`
enforces that separation — it is the mechanism that keeps "what the item says"
distinct from "what we conclude from it".

Inputs
------
* `record` — enriched by preprocess and (when available) frame analysis.
* `context`, `codebook_entries`, `model`, `prompt_version`, `project_profile`.

Outputs
-------
* returns the summary proposal (the caller passes it to postprocess);
* writes `record.human_readable.summary / generated_at / markdown` — the
  researcher-facing description;
* stage output `multimodal_synthesis` with the full proposal, prompt provenance
  and model-run metadata;
* appends to `record.analysis.model_runs`.
"""
from __future__ import annotations

from ..canonical import CanonicalRecord
from ..codebooks import CodebookEntry
from ..llm.structured_output import chat_structured
from ..prompt_library import load_prompt, prompt_provenance
from ..social_semiotic import MultimodalSummaryProposal, assert_preanalysis_boundary
from .prompt_map import phase1_preanalysis_prompt_ids
from .proposals import SummaryResult
from .shared import (
    PipelineContext,
    append_stage,
    envelope_for_stage,
    model_run_metadata,
    now_iso,
)


def _summary_markdown(proposal: MultimodalSummaryProposal) -> str:
    """Render the description a researcher reads in the dashboard/export.

    The markdown keeps the intermodal relations and the model's own stated
    limitations, so a reader sees what the description was based on and where it
    may be weak — rather than only the fluent final sentence.
    """
    parts = [
        "# Multimodal social-semiotic pre-analysis",
        proposal.cross_modal_synthesis or proposal.narrative or proposal.summary,
    ]
    if proposal.intermodal_relations:
        relations = "\n".join(
            f"- {item.relation_type}: {item.description}"
            for item in proposal.intermodal_relations
        )
        parts.extend(("## Intermodal relations", relations))
    if proposal.limitations:
        parts.extend(("## Limitations", "\n".join(f"- {x}" for x in proposal.limitations)))
    return "\n\n".join(part for part in parts if part).strip()


def summarize_record(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext,
    codebook_entries: list[CodebookEntry],
    model: str,
    prompt_version: str,
    project_profile: str,
    allow_cloud_fallback: bool | None,
) -> SummaryResult:
    """Run the descriptive pass and store it as the record's summary."""
    system_id, task_id = phase1_preanalysis_prompt_ids("summary")
    system_resource = load_prompt(system_id, version="v2")
    task_resource = load_prompt(task_id, version="v2")
    rendered_task = task_resource.render(
        project_note=f"{project_profile.upper()} source context only; remain descriptive."
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
        MultimodalSummaryProposal,
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
        stage="social_semiotic_summary",
    )

    now = now_iso()
    record.human_readable.summary = proposal.summary
    record.human_readable.generated_at = now
    record.human_readable.markdown = _summary_markdown(proposal)
    record.analysis.model_runs.append(run_meta)
    append_stage(
        record,
        "multimodal_synthesis",
        {
            "created_at": now,
            "prompt_version": prompt_version,
            **prompt_meta,
            "context_provenance": envelope.provenance_snapshot(),
            "proposal": proposal.model_dump(mode="json"),
            "model_run": run_meta,
        },
    )
    return proposal
