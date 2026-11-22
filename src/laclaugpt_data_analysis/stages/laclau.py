"""Stage 3 — laclau: the Laclau/Mouffe discourse analysis.

Purpose
-------
Turn a *description* of an item into an *analysis* of it: which demands are
articulated, around which nodal points, between which collective subjects, along
which frontiers, and whether the articulation is populist in the sense the
project tests. This is the theory-bearing stage; every other stage is either
preparation for it or bookkeeping after it.

Why it is last among the model stages
-------------------------------------
It is the most interpretive step, so it must consume a description it did not
write. It reads the record as enriched by preprocess and described by the
summary stage. Nothing downstream of it may re-decide what the description was.

Scientific boundary
-------------------
This stage may classify in the project's theoretical vocabulary (formations,
imaginaries, populism). It must not invent evidence: no claim is accepted without
a quotation that the code can point at in the source. See
`stages/evidence.py` for how that is enforced — the check lives there rather than
here so the rule applies to every stage that cites evidence.

Inputs
------
* `record` with the descriptive layers already attached;
* `context`, `codebook_entries`, `model`, `prompt_version`, `project_profile`.

Outputs
-------
* returns the `DiscourseProposal`;
* stage output `discourse_analysis` with proposal + prompt provenance + model-run
  metadata, recorded before postprocess reads anything from it.
"""
from __future__ import annotations

from typing import Any

from ..canonical import CanonicalRecord
from ..codebooks import CodebookEntry
from ..llm.structured_output import chat_structured
from ..prompt_library import load_prompt, prompt_provenance
from .evidence_policy import (
    apply_corrections,
    apply_verbatim_policy,
    build_correction_prompt,
    proposal_quotes,
)
from .prompt_map import prompt_ids_for_stage
from .proposals import DiscourseProposal, EvidenceCorrectionProposal
from .shared import (
    PipelineContext,
    append_stage,
    envelope_for_stage,
    model_run_metadata,
    now_iso,
    render_prompt,
)


def discourse_analysis(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext,
    codebook_entries: list[CodebookEntry],
    model: str,
    prompt_version: str,
    project_profile: str,
    allow_cloud_fallback: bool | None,
) -> DiscourseProposal:
    """Run the theory stage and record it as a proposal, not a finding."""
    system_id, task_id = prompt_ids_for_stage(project_profile, "discourse")
    system_resource = load_prompt(system_id, version="v1")
    task_resource = load_prompt(
        task_id,
        version=("v3" if project_profile.casefold() == "ai26" else "v2" if project_profile.casefold() == "ep24" else "v1"),
    )
    rendered_task = task_resource.render(
        project_note="AI26 discourse analysis." if project_profile.casefold() == "ai26" else "(none)"
    )
    envelope = envelope_for_stage(
        record,
        context,
        task=rendered_task.text,
        codebook_entries=codebook_entries,
        prompt_version=prompt_version,
    )
    user_prompt, prompt_report = render_prompt(envelope, stage="discourse")
    proposal, response = chat_structured(
        provider,
        DiscourseProposal,
        model=model,
        system_prompt=system_resource.text,
        user_prompt=user_prompt,
        allow_cloud_fallback=allow_cloud_fallback,
    )
    # #458 / D6: verify the evidence the model claims, allow ONE evidence-only correction and
    # then abstain. Best effort by design: a provider that cannot answer the correction must
    # not fail the stage, but the failure is recorded rather than hidden.
    text = record.content.text or ""
    correction: dict[str, Any] = {"attempted": False}
    try:
        verdict = apply_verbatim_policy(text, proposal_quotes(proposal))
        if verdict.unlocatable:
            correction["attempted"] = True
            corrected, _ = chat_structured(
                provider,
                EvidenceCorrectionProposal,
                model=model,
                system_prompt=system_resource.text,
                user_prompt=build_correction_prompt(text, verdict.unlocatable),
                allow_cloud_fallback=allow_cloud_fallback,
            )
            replacements = {
                pair.original.strip(): pair.verbatim
                for pair in corrected.corrections
                if pair.original.strip() and pair.verbatim.strip()
            }
            proposal, replaced = apply_corrections(proposal, replacements)
            after = apply_verbatim_policy(text, proposal_quotes(proposal))
            correction.update({"replaced": replaced, "unresolved": len(after.unlocatable)})
        else:
            correction["unresolved"] = 0
    except Exception as exc:  # noqa: BLE001 - telemetry must survive any provider failure
        correction["error"] = f"{type(exc).__name__}: {exc}"[:200]
    prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
    run_meta = model_run_metadata(
        context,
        response,
        prompt_meta,
        prompt_version=prompt_version,
        stage="discourse",
        prompt_report=prompt_report,
    )
    append_stage(
        record,
        "discourse_analysis",
        {
            "created_at": now_iso(),
            "prompt_version": prompt_version,
            **prompt_meta,
            "context_provenance": envelope.provenance_snapshot(),
            "prompt_budget": prompt_report,
            "evidence_correction": correction,
            "proposal": proposal.model_dump(mode="json"),
            "model_run": run_meta,
        },
    )
    record.analysis.model_runs.append(run_meta)
    return proposal
