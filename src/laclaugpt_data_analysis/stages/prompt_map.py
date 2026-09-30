"""Which prompt each stage uses, per corpus profile.

Kept apart from the stages so a researcher can answer "what is the model actually
being asked to do?" in one place, and so adding a corpus does not mean editing
every stage.

Prompt *text* lives in `../prompts/` as markdown; this module only maps a
(stage, project profile) to the prompt id and version. Prompt files are the
research instrument — they are versioned, hashed and recorded in the model-run
provenance for every call, so a stored result can always be traced to the exact
wording that produced it.

Reading this module answers:
* which prompt family a corpus uses (EP24 keeps its own legacy prompts);
* where the descriptive pre-analysis phases and the theory phase differ;
* why a stage is unavailable for a profile.
"""
from __future__ import annotations

# Prompts shared across corpora for the descriptive first pass.
_PREANALYSIS_PROMPTS = {
    "frame": ("multimodal.system", "multimodal.frame_analysis"),
    "summary": ("multimodal.system", "multimodal.summary_analysis"),
}


def prompt_ids_for_stage(project_profile: str, stage: str) -> tuple[str, str]:
    """Return `(system_prompt_id, task_prompt_id)` for a stage.

    EP24 keeps its historical prompt set for reproducibility: re-running an EP24
    analysis must ask the model the same question as the published run, so those
    ids are deliberately not repointed at the modern prompts.
    """
    profile = project_profile.casefold()

    if profile == "ep24":
        ep24_tasks = {
            "frame": ("laclau.system", "ep24.frame_analysis"),
            "summary": ("laclau.system", "ep24.summary_analysis"),
            "discourse": ("laclau.system", "ep24.laclau_analysis"),
        }
        if stage in ep24_tasks:
            return ep24_tasks[stage]

    if stage == "frame":
        return (
            ("multimodal.system", "multimodal.frame_analysis")
            if profile == "ai26"
            else ("laclau.system", "laclau.frame_analysis")
        )
    if stage == "summary":
        return (
            ("multimodal.system", "multimodal.summary_analysis")
            if profile == "ai26"
            else ("laclau.system", "laclau.summary_analysis")
        )
    if stage == "discourse":
        return "laclau.system", "laclau.discourse_analysis"
    raise ValueError(f"unsupported canonical pipeline stage: {stage}")


def phase1_preanalysis_prompt_ids(stage: str) -> tuple[str, str]:
    """Current Phase 1 descriptive prompt family, independent of corpus profile.

    Phase 1 pre-analysis is corpus-agnostic by design: the *same* descriptive
    question is asked of every corpus, so the resulting descriptions stay
    comparable. Corpus-specific instruction enters later, at the theory stage.
    """
    try:
        return _PREANALYSIS_PROMPTS[stage]
    except KeyError as exc:
        raise ValueError(f"unsupported Phase 1 pre-analysis stage: {stage}") from exc


__all__ = ["phase1_preanalysis_prompt_ids", "prompt_ids_for_stage"]
