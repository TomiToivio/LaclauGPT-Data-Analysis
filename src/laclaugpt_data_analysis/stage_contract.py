"""Project analysis-stage contract validation and provenance helpers.

Project configuration is executable intent, not decoration. A stage declared enabled
must correspond to an implemented canonical capability; unavailable/planned stages fail
before model work starts instead of silently producing empty analysis fields.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StageCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    flag: str
    status: str
    runtime_stage: str | None = None
    output_fields: tuple[str, ...] = ()
    prompt_keys: tuple[str, ...] = ()
    note: str = ""


STAGE_CAPABILITIES: dict[str, StageCapability] = {
    "laclau": StageCapability(
        flag="laclau",
        status="implemented",
        runtime_stage="discourse",
        output_fields=(
            "signifiers",
            "nodal_points",
            "floating_signifiers",
            "empty_signifier_candidates",
            "formations",
            "imaginaries",
            "relations",
            "equivalence_chains",
            "difference_chains",
            "antagonisms",
            "us",
            "frontier",
            "affects",
        ),
        prompt_keys=("discourse",),
    ),
    "palonen": StageCapability(
        flag="palonen",
        status="implemented",
        runtime_stage="discourse",
        output_fields=("formula_of_populism", "frontier", "us"),
        prompt_keys=("discourse",),
        note="Implemented inside the shared Laclau/Mouffe/Palonen discourse stage.",
    ),
    "sociotechnical_imaginaries": StageCapability(
        flag="sociotechnical_imaginaries",
        status="implemented",
        runtime_stage="discourse",
        output_fields=("imaginaries",),
        prompt_keys=("discourse",),
    ),
    "sentiment": StageCapability(
        flag="sentiment",
        status="implemented",
        runtime_stage="summary",
        output_fields=("sentiments",),
        prompt_keys=("summary",),
    ),
    "topics": StageCapability(
        flag="topics",
        status="implemented",
        runtime_stage="summary",
        output_fields=("topics",),
        prompt_keys=("summary",),
    ),
    "entities": StageCapability(
        flag="entities",
        status="implemented",
        runtime_stage="summary",
        output_fields=("entities",),
        prompt_keys=("summary",),
    ),
    "context_memory": StageCapability(
        flag="context_memory",
        status="implemented",
        runtime_stage="context",
        note="Controls use of supplied memory context; retrieval remains an entrypoint concern.",
    ),
    "temporal": StageCapability(
        flag="temporal",
        status="implemented",
        runtime_stage="summary",
        note="Temporal/event observations are retained in summary-stage output and provenance.",
        prompt_keys=("summary",),
    ),
    "multimodal": StageCapability(
        flag="multimodal",
        status="implemented",
        runtime_stage="frame",
        output_fields=("representations",),
        prompt_keys=("frame", "summary"),
        note="Frame analysis runs when frames are present; text-only records remain valid.",
    ),
    "sna": StageCapability(flag="sna", status="excluded", note="Deliberately excluded from AI26."),
    "ant": StageCapability(flag="ant", status="excluded", note="Deliberately excluded from AI26."),
    "valueflows": StageCapability(
        flag="valueflows", status="excluded", note="Deliberately excluded from AI26."
    ),
    "dna_statement_coding": StageCapability(
        flag="dna_statement_coding",
        status="implemented",
        runtime_stage="dna_statement_coding",
        prompt_keys=("dna",),
    ),
    "critical_ai": StageCapability(
        flag="critical_ai",
        status="implemented",
        runtime_stage="critical_ai",
        prompt_keys=("critical_ai",),
    ),
}


def _enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return bool(value.get("enabled", False))
    return False


def resolve_stage_contract(project_config: dict[str, Any]) -> dict[str, Any]:
    """Validate project analysis flags and return the effective auditable contract."""
    analysis = project_config.get("analysis") or {}
    if not isinstance(analysis, dict):
        raise ValueError("project_config.analysis must be an object")

    unknown = sorted(set(analysis) - set(STAGE_CAPABILITIES))
    if unknown:
        raise ValueError("unknown project analysis flags: " + ", ".join(unknown))

    enabled: list[str] = []
    disabled: list[str] = []
    statuses: dict[str, str] = {}
    output_fields: dict[str, list[str]] = {}
    runtime_stages: list[str] = []

    for flag, capability in STAGE_CAPABILITIES.items():
        if flag not in analysis:
            continue
        is_enabled = _enabled(analysis[flag])
        statuses[flag] = capability.status
        output_fields[flag] = list(capability.output_fields)
        if is_enabled:
            if capability.status != "implemented":
                raise ValueError(
                    f"analysis.{flag}=true but capability status is {capability.status!r}"
                )
            enabled.append(flag)
            if capability.runtime_stage and capability.runtime_stage not in runtime_stages:
                runtime_stages.append(capability.runtime_stage)
        else:
            disabled.append(flag)

    return {
        "enabled_flags": enabled,
        "disabled_flags": disabled,
        "statuses": statuses,
        "runtime_stages": runtime_stages,
        "output_fields": output_fields,
    }


def stage_enabled(project_config: dict[str, Any], flag: str, *, default: bool = True) -> bool:
    analysis = project_config.get("analysis") or {}
    if not isinstance(analysis, dict) or flag not in analysis:
        return default
    return _enabled(analysis[flag])
