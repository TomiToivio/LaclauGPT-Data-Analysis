"""Shared infrastructure for the Phase 1 analysis stages.

Everything in this module is *plumbing*, not research logic. A researcher reading
`preprocess.py`, `frame.py`, `summary.py`, `laclau.py` or `postprocess.py` should
not have to wade through it; an engineer follows imports here when they need to
know how a stage is wired.

What lives here:

* `PipelineContext` — the per-run inputs a stage needs beyond the record itself
  (project/memory/RAG context, codebook and config revisions, the project's
  capability configuration).
* `append_stage` — how a stage records what it did into the record's audit trail.
* `envelope_for_stage` — builds the prompt envelope (the layered system/context/task
  stack documented in `prompts/README.md`) that every model-calling stage sends.
* `model_run_metadata` — the provenance block attached to every model call, so a
  result can be traced back to the exact prompt, config revision and model.
* Capability resolution (`enabled`, `effective_stage_set`, phase gating) — which
  optional analysis capabilities a project has switched on.

Nothing here calls a model or decides anything about the research method.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from ..canonical import CanonicalRecord
from ..codebooks import CodebookEntry
from ..context_envelope import PromptEnvelope, build_prompt_envelope

# ---------------------------------------------------------------------------
# Run context
# ---------------------------------------------------------------------------


class PipelineContext(BaseModel):
    """Everything a stage needs beyond the record being analysed.

    Context layers are kept separate rather than pre-merged because their
    *trust roles* differ: project context is framing, memory context is
    continuity (never source evidence), RAG context is retrieved background.
    Merging them early would destroy the distinction the audit trail depends on.
    """

    project_context: str = ""
    source_context: str = ""
    situational_context: str = ""
    memory_context: str = ""
    rag_context: str = ""
    provenance: dict[str, list[str]] = Field(default_factory=dict)
    config_revision: str = ""
    codebook_revision: str = ""
    context_revision: str = ""
    project_config_revision: str = ""
    project_config: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stage output ports (infrastructure boundaries, not research decisions)
# ---------------------------------------------------------------------------


class GraphSink(Protocol):
    """Destination for the per-record discourse graph (optional)."""

    def write_graph(self, source_url: str, graph: dict[str, Any]) -> None: ...


class VectorSink(Protocol):
    """Destination for the record's embedding (optional)."""

    def upsert(self, source_url: str, text: str, metadata: dict[str, Any]) -> None: ...


# A preprocessor enriches a record with derived inputs (ASR, OCR, frames,
# translations) before the model stages run. It is injected rather than
# hard-coded so the same pipeline runs on a laptop, CSC Roihu or a server.
Preprocessor = Callable[[CanonicalRecord], dict[str, Any] | None]


# ---------------------------------------------------------------------------
# Capability configuration
# ---------------------------------------------------------------------------

# Maps a project capability flag (as written in a project's analysis config) to
# the pipeline surface it switches on. Phase 2 methods are listed explicitly so
# an unknown flag is reported rather than silently ignored.
_AI26_CAPABILITIES = {
    "laclau": "discourse",
    "palonen": "discourse",
    "sociotechnical_imaginaries": "discourse",
    "sentiment": "summary_projection",
    "topics": "summary_projection",
    "entities": "summary_projection",
    "context_memory": "context",
    "temporal": "summary",
    "multimodal": "frame_summary",
    "sna": "phase2_optional",
    "ant": "phase2_optional",
    "valueflows": "phase2_optional",
}

# Methods held back behind Phase 2. They must never enter the Phase 1 default
# path: they are opt-in, and a project must declare analysis_phase >= 2.
_PHASE2_CAPABILITIES = frozenset(
    {"sna", "ant", "valueflows", "dna_statement_coding", "critical_ai"}
)


def analysis_flags(context: PipelineContext) -> dict[str, Any]:
    """Return the project's declared analysis capabilities, if any."""
    analysis = context.project_config.get("analysis") if context.project_config else None
    return dict(analysis) if isinstance(analysis, dict) else {}


def analysis_phase(context: PipelineContext) -> int:
    """Return the project's declared analysis phase (default 1)."""
    value = context.project_config.get("analysis_phase", 1) if context.project_config else 1
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("analysis_phase must be an integer") from exc


def phase_allows(context: PipelineContext, key: str) -> bool:
    """True when a capability is permitted at the project's declared phase."""
    return key not in _PHASE2_CAPABILITIES or analysis_phase(context) >= 2


def enabled(context: PipelineContext, key: str, *, default: bool = True) -> bool:
    """Resolve whether a capability is switched on for this run.

    A capability counts as enabled only when it is BOTH declared by the project
    AND permitted at the current phase. Absence of configuration is never read
    as activation for the expensive or theory-specific stages; callers pass
    `default=False` for those.
    """
    flags = analysis_flags(context)
    if key in flags:
        value = flags[key]
    elif key == "multimodal" and context.project_config and key in context.project_config:
        # Compatibility with the pre-analysis config shape used before
        # project_config.analysis became the canonical capability namespace.
        # It is still an explicit opt-in, never an inferred activation.
        value = context.project_config[key]
    else:
        value = default
    configured = bool(value.get("enabled", default)) if isinstance(value, dict) else bool(value)
    return configured and phase_allows(context, key)


def effective_stage_set(context: PipelineContext) -> list[str]:
    """List the analysis stages this run will actually execute.

    Recorded on every result so a downstream reader can tell which stages ran
    without inferring it from the shape of the output.
    """
    stages: list[str] = []
    for key, implementation in _AI26_CAPABILITIES.items():
        if enabled(context, key, default=False) and implementation:
            stages.append(key)
    for key in ("dna_statement_coding", "critical_ai"):
        if enabled(context, key, default=False):
            stages.append(key)
    return sorted(stages)


def validate_project_analysis_config(context: PipelineContext) -> None:
    """Reject an analysis config that names a capability the pipeline lacks.

    A typo in a project's analysis config would otherwise silently disable a
    stage, so this fails loudly instead.
    """
    flags = analysis_flags(context)
    if not flags:
        return
    unknown = sorted(
        set(flags) - set(_AI26_CAPABILITIES) - {"dna_statement_coding", "critical_ai"}
    )
    if unknown:
        raise ValueError(f"unknown analysis capability flag(s): {', '.join(unknown)}")
    phase = analysis_phase(context)
    if phase < 1:
        raise ValueError("analysis_phase must be >= 1")


# ---------------------------------------------------------------------------
# Stage bookkeeping
# ---------------------------------------------------------------------------


def append_stage(record: CanonicalRecord, name: str, payload: dict[str, Any]) -> None:
    """Append one entry to the record's stage audit trail.

    The trail is append-only per stage: re-running a stage records a second
    entry rather than overwriting the first, so a retry stays visible.
    """
    existing = record.intermediate.stage_outputs.get(name)
    history = existing if isinstance(existing, list) else ([] if existing is None else [existing])
    history.append(payload)
    record.intermediate.stage_outputs[name] = history


def now_iso() -> str:
    """UTC timestamp used for stage records."""
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Prompt envelope + model provenance
# ---------------------------------------------------------------------------


def memory_text(entries: list[CodebookEntry]) -> str:
    """Render codebook entries as a compact memory block for the prompt."""
    lines = []
    for entry in entries:
        aliases = ", ".join(entry.aliases)
        lines.append(
            f"- {entry.kind}: {entry.label}" + (f" (aliases: {aliases})" if aliases else "")
        )
    return "\n".join(lines)


def envelope_for_stage(
    record: CanonicalRecord,
    context: PipelineContext,
    *,
    task: str,
    codebook_entries: list[CodebookEntry],
    prompt_version: str,
) -> PromptEnvelope:
    """Assemble the layered prompt envelope for one stage call.

    Memory context and codebook entries share the memory layer; the task text is
    the current operation. See `prompts/README.md` for the three-layer model.
    """
    memory = "\n".join(
        part for part in (context.memory_context, memory_text(codebook_entries)) if part
    )
    return build_prompt_envelope(
        record,
        task=task,
        project_context=context.project_context,
        source_context=context.source_context,
        situational_context=context.situational_context,
        memory_context=memory,
        rag_context=context.rag_context,
        context_provenance=context.provenance,
        prompt_version=prompt_version,
    )


def project_config_sha256(context: PipelineContext) -> str:
    """Stable hash of the project configuration in force for this run."""
    if not context.project_config:
        return ""
    payload = json.dumps(context.project_config, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def model_run_metadata(
    context: PipelineContext,
    response,
    prompt_meta: dict[str, Any],
    *,
    prompt_version: str,
    stage: str,
) -> dict[str, Any]:
    """Provenance block attached to every model call.

    Carries the prompt identity/version, the revisions in force, and the
    effective stage set, so a stored result can be reproduced and audited.
    """
    return {
        **response.provenance.to_dict(),
        "prompt_version": prompt_version,
        "stage": stage,
        "config_revision": context.config_revision,
        "codebook_revision": context.codebook_revision,
        "context_revision": context.context_revision,
        "project_config_revision": context.project_config_revision,
        "project_config_sha256": project_config_sha256(context),
        "effective_analysis_stages": effective_stage_set(context),
        **prompt_meta,
    }
