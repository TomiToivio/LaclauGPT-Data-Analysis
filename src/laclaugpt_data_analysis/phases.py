"""Phase gating for the LaclauGPT analysis pipeline.

The LaclauGPT analysis pipeline descends from the legacy EP24 multimodal
pipeline::

    puhti_preprocess.py -> puhti_frame.py -> puhti_summary.py
        -> puhti_populism.py -> puhti_postprocess.py

Issue #140 makes that five-stage order the **default analysis path** (Phase 1)
and marks later, theory-heavy and network methods as **Phase 2** — available,
but experimental, optional and off by default.

This module is the single source of truth for:

* the canonical Phase 1 stage order (``PHASE1_STAGE_ORDER``);
* which stages are Phase 1 vs Phase 2 (``STAGE_PHASES``);
* which capabilities are Phase 2 and must not enter the default pipeline
  (``PHASE2_CAPABILITIES``).

It is deliberately declarative: importing it performs no work, reads no
configuration and contacts nothing. The canonical pipeline consults it so that
"runs by default" is an explicit, testable contract rather than an accident of
dictionary ordering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StageName = Literal["preprocess", "frame", "summary", "discourse", "postprocess"]

#: The canonical Phase 1 execution order. This is the default analysis path.
#: ``frame`` is conditional: it runs only when a record actually carries
#: images, video or extracted frames.
PHASE1_STAGE_ORDER: tuple[str, ...] = (
    "preprocess",
    "frame",
    "summary",
    "discourse",
    "postprocess",
)

#: Stages that are inherently conditional. They are part of Phase 1 but are
#: skipped cleanly when their input is absent (e.g. text-only records).
CONDITIONAL_STAGES: frozenset[str] = frozenset({"frame"})

#: Capabilities that belong to Phase 2 and must never run unless a project
#: explicitly enables them. Enabling an unimplemented one stays a config error.
PHASE2_CAPABILITIES: frozenset[str] = frozenset(
    {
        "dna_statement_coding",
        "critical_ai",
        "sna",
        "ant",
        "valueflows",
    }
)

#: Plugin-spec capabilities that are Phase 2/experimental rather than Phase 1.
#: These are the AC/DT compatibility and network methods.
PHASE2_PLUGIN_METHODS: frozenset[str] = frozenset(
    {
        "social_network_analysis",
        "actor_network",
        "hashtag_cooccurrence",
        "peak_analysis",
        "close_reading_sampler",
        "word_frequency",
    }
)


@dataclass(frozen=True, slots=True)
class StagePhase:
    """Declarative phase metadata for one pipeline stage."""

    name: str
    phase: int
    default_enabled: bool
    experimental: bool
    optional: bool
    conditional: bool
    legacy_origin: str
    summary: str

    @property
    def runs_by_default(self) -> bool:
        """True when the stage participates in the default Phase 1 run."""
        return self.phase == 1 and self.default_enabled


#: Phase metadata for every stage in the conceptual Phase 1 pipeline.
#: The ``legacy_origin`` values record the descended-from EP24 script so the
#: modern implementation stays recognisably linked to its ancestor.
STAGE_PHASES: dict[str, StagePhase] = {
    "preprocess": StagePhase(
        name="preprocess",
        phase=1,
        default_enabled=True,
        experimental=False,
        optional=False,
        conditional=False,
        legacy_origin="puhti_preprocess.py",
        summary=(
            "Media preprocessing: transcription, OCR, keyframe extraction and "
            "normalization of multimodal evidence for downstream stages."
        ),
    ),
    "frame": StagePhase(
        name="frame",
        phase=1,
        default_enabled=True,
        experimental=False,
        optional=False,
        conditional=True,
        legacy_origin="puhti_frame.py",
        summary=(
            "Conditional descriptive frame analysis. Runs only when a record "
            "carries images, video or extracted frames."
        ),
    ),
    "summary": StagePhase(
        name="summary",
        phase=1,
        default_enabled=True,
        experimental=False,
        optional=False,
        conditional=False,
        legacy_origin="puhti_summary.py",
        summary=(
            "Structured research-oriented summary over source material, "
            "metadata, transcript/OCR and frame-analysis outputs. An "
            "intermediate layer, not the final Laclaudian interpretation."
        ),
    ),
    "discourse": StagePhase(
        name="discourse",
        phase=1,
        default_enabled=True,
        experimental=False,
        optional=False,
        conditional=False,
        legacy_origin="puhti_populism.py",
        summary=(
            "Theory-guided Laclaudian discourse analysis: evidence-linked "
            "candidates for signifiers, articulations, demands, subjects, "
            "chains, frontiers and affects. Provisional pre-analysis."
        ),
    ),
    "postprocess": StagePhase(
        name="postprocess",
        phase=1,
        default_enabled=True,
        experimental=False,
        optional=False,
        conditional=False,
        legacy_origin="puhti_postprocess.py",
        summary=(
            "Final structured normalization/extraction over prior outputs into "
            "typed, auditable machine-readable fields for validation, export, "
            "comparison and visualization."
        ),
    ),
}

#: Phase 2 stages are declared here for documentation/testing completeness, but
#: they have no position in the Phase 1 default order.
PHASE2_STAGES: dict[str, StagePhase] = {
    name: StagePhase(
        name=name,
        phase=2,
        default_enabled=False,
        experimental=True,
        optional=True,
        conditional=False,
        legacy_origin="",
        summary="Phase 2 / experimental / optional. Off by default.",
    )
    for name in ("dna_statement_coding", "critical_ai", "sna", "ant", "valueflows")
}


def stage_phase(name: str) -> StagePhase:
    """Return the declared phase metadata for a stage name."""
    if name in STAGE_PHASES:
        return STAGE_PHASES[name]
    if name in PHASE2_STAGES:
        return PHASE2_STAGES[name]
    raise KeyError(f"unknown pipeline stage: {name}")


def is_phase1_stage(name: str) -> bool:
    return stage_phase(name).phase == 1


def is_phase2_capability(name: str) -> bool:
    return name in PHASE2_CAPABILITIES


def default_stage_order() -> tuple[str, ...]:
    """The Phase 1 default execution order (conditional stages included)."""
    return PHASE1_STAGE_ORDER


def phase_manifest() -> dict[str, object]:
    """Machine-readable phase manifest for documentation and tests."""
    return {
        "phase1_order": list(PHASE1_STAGE_ORDER),
        "conditional": sorted(CONDITIONAL_STAGES),
        "phase2_capabilities": sorted(PHASE2_CAPABILITIES),
        "stages": {
            name: {
                "phase": meta.phase,
                "default_enabled": meta.default_enabled,
                "experimental": meta.experimental,
                "optional": meta.optional,
                "conditional": meta.conditional,
                "legacy_origin": meta.legacy_origin,
            }
            for name, meta in STAGE_PHASES.items()
        },
    }
