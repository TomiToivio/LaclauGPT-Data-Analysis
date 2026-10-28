"""Pipeline registry: explicit selection of analysis implementations (#399).

The repository used to have one runnable pipeline, so "which analysis runs" was never a question.
Importing EP24-current and EP24-legacy next to AI26 makes it one, and a silent default would be a
scientific hazard: the same input record analysed by a different implementation is a different result.

Rules encoded here:

* Every pipeline has a stable id. ``get_pipeline`` raises ``UnknownPipeline`` instead of falling back,
  so a typo cannot quietly run something else.
* A pipeline knows where it came from (repository, ref, exact SHA) and which package holds the
  imported code, so provenance is a lookup rather than an archaeology exercise.
* Execution keys carry the pipeline id. Two pipelines analysing the same record must not share queues,
  leases, artifact prefixes or result collections — otherwise the faster one silently completes the
  other's work.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "PIPELINES",
    "PipelineSpec",
    "UnknownPipeline",
    "get_pipeline",
    "list_pipelines",
    "pipeline_keys",
    "validate_pipeline_id",
]

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")

AI26_STAGES = (
    "0-handoff-preflight",
    "1-preprocess",
    "2-frame",
    "3-video",
    "4-summary",
    "5-postprocess",
    "6-laclau",
    "7-dna",
    "8-sna",
    "9-export",
)


@dataclass(frozen=True)
class PipelineSpec:
    """One selectable analysis implementation."""

    pipeline_id: str
    label: str
    package: str
    stages: tuple[str, ...]
    source_repository: str
    source_ref: str
    source_sha: str
    notes: str = ""
    #: ``in-process`` = importable library code; ``script`` = operational scripts executed as
    #: programs. The EP24 snapshots are scripts: they read CSV/SQLite inputs and parse argv at
    #: module level, so importing them would run analysis rather than define it.
    execution: str = "in-process"
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def legacy(self) -> bool:
        return "legacy" in self.pipeline_id


MULTIMODAL = "https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis"

PIPELINES: dict[str, PipelineSpec] = {
    "ai26": PipelineSpec(
        pipeline_id="ai26",
        label="AI26 canonical analysis (in-repository implementation)",
        package="laclaugpt_data_analysis",
        stages=AI26_STAGES,
        source_repository="https://github.com/TomiToivio/LaclauGPT-Data-Analysis",
        source_ref="main",
        source_sha="in-tree",
        notes="The production pipeline. Its behaviour is unchanged by the multi-pipeline work.",
    ),
    "ep24": PipelineSpec(
        pipeline_id="ep24",
        label="EP24 current (Roihu Step 0-9)",
        package="laclaugpt_data_analysis.pipelines.ep24.vendor",
        stages=(
            "0-import",
            "1-preprocess",
            "2-frame",
            "3-video",
            "4-summary",
            "5-postprocess",
            "6-discourse-analysis",
            "7-discourse-network",
            "8-social-network",
            "9-rdf",
        ),
        source_repository=MULTIMODAL,
        source_ref="main",
        source_sha="db123759fe21b194275d87d6ccc3b7c4f98a2055",
        notes="Snapshot import; see docs/EP24_SOURCE_INVENTORY.json for the file-level SHA-256 map.",
        execution="script",
    ),
    "ep24-legacy": PipelineSpec(
        pipeline_id="ep24-legacy",
        label="EP24 legacy (Puhti-era implementation)",
        package="laclaugpt_data_analysis.pipelines.ep24_legacy.vendor",
        stages=("preprocess", "frame", "summary", "populism", "postprocess"),
        source_repository=MULTIMODAL,
        source_ref="legacy",
        source_sha="e011c34274c41923e801c32c824c5afa7468e1a1",
        notes=(
            "Historical algorithms preserved verbatim. Stage names differ from current EP24 on purpose: "
            "the legacy pipeline has no separate discourse/network/RDF steps."
        ),
        execution="script",
    ),
}


class UnknownPipeline(LookupError):
    """Raised instead of defaulting when a pipeline id does not exist."""


def validate_pipeline_id(pipeline_id: str) -> str:
    if not _ID.fullmatch(str(pipeline_id or "")):
        raise ValueError(f"invalid pipeline id: {pipeline_id!r}")
    return str(pipeline_id)


def list_pipelines() -> list[PipelineSpec]:
    """All selectable pipelines, ordered by id for stable output."""
    return [PIPELINES[key] for key in sorted(PIPELINES)]


def get_pipeline(pipeline_id: str) -> PipelineSpec:
    """Resolve a pipeline id, refusing to guess."""
    key = str(pipeline_id or "").strip()
    try:
        return PIPELINES[key]
    except KeyError:
        known = ", ".join(sorted(PIPELINES))
        raise UnknownPipeline(f"unknown pipeline {key!r}; known pipelines: {known}") from None


def pipeline_keys(*, pipeline_id: str, project_id: str, run_id: str) -> dict[str, str]:
    """Execution keys for one pipeline run.

    Every namespace segment includes the pipeline id, so the same record analysed by EP24 and
    EP24-legacy cannot collide in Redis, MongoDB or Allas even when the run id is identical.
    """
    spec = get_pipeline(pipeline_id)
    project = validate_pipeline_id(project_id)
    run = str(run_id or "").strip()
    if not run:
        raise ValueError("run_id is required")
    if "/" in run or ":" in run:
        raise ValueError(f"run_id must not contain ':' or '/': {run!r}")
    scope = f"{project}:{spec.pipeline_id}:{run}"
    return {
        "scope": scope,
        "redis_stream": f"laclaugpt:{scope}:stream:tasks",
        "redis_group": f"laclaugpt:{scope}:group:workers",
        "redis_dead_letter": f"laclaugpt:{scope}:stream:dead",
        "redis_worker_key": f"laclaugpt:{scope}:worker",
        "mongo_results": f"{project}__{spec.pipeline_id}__analysis_results",
        "mongo_failures": f"{project}__{spec.pipeline_id}__analysis_failures",
        "s3_prefix": f"{project}/{spec.pipeline_id}/{run}",
    }
