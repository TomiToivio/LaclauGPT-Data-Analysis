"""Pipeline registry: several scientific pipelines, one analysis repository (#399).

Before this module the repository had one runnable pipeline. AI26 was the implementation,
not an entry in a catalogue, so "run EP24" meant running a different checkout. The
registry makes a pipeline an explicit, named choice:

    ai26         — the current AI26 canonical stages (unchanged behaviour)
    ep24         — the current EP24 Roihu Step 0–9 implementation, imported from upstream
    ep24-legacy  — the historical Puhti-era EP24 implementation, imported from upstream

Design rules, each of which exists because the alternative fails quietly:

* **Explicit selection.** There is no fallback and no default-by-accident; a caller must
  name the pipeline it intends to run.
* **Frozen snapshots, not branch references.** Each EP24 implementation is vendored at a
  pinned commit with a per-file hash in ``PROVENANCE.json``. A runtime dependency on an
  upstream branch would mean the "historical" implementation silently changing.
* **Four distinct identities.** Project/dataset, pipeline implementation version,
  scientific configuration/codebook version and run id are separate. Outputs from two
  versions analysing the same records must stay distinguishable, so the pipeline id is
  part of every durable key, not metadata attached afterwards.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class PipelineSpec:
    """Everything needed to identify, check and run one pipeline version."""

    pipeline_id: str
    version: str
    display_name: str
    stages: tuple[str, ...]
    stage_prefix: str
    entry_module: str | None = None
    snapshot_dir: str | None = None
    source_repository: str = "TomiToivio/LaclauGPT-Data-Analysis"
    source_ref: str = ""
    license: str = "See upstream repository"
    requires: tuple[str, ...] = ()
    notes: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def snapshot_path(self) -> Path | None:
        return PACKAGE_DIR / self.snapshot_dir if self.snapshot_dir else None

    def stages_present(self) -> list[str]:
        """Which declared stages actually exist on disk.

        Declared-but-missing is a real failure mode: a pipeline that lists ten stages and
        ships nine looks complete in a registry listing and fails at stage ten.
        """
        snapshot = self.snapshot_path
        if snapshot is None:
            return list(self.stages)
        src = snapshot / "src"
        return [s for s in self.stages if (src / s).is_file() or (src / f"{s}.py").is_file()]


AI26_STAGES = (
    "preprocess", "frame", "summary", "laclau", "evidence", "graph", "postprocess",
)

EP24_STAGES = (
    "step_0_roihu_import", "step_1_roihu_preprocess", "step_2_roihu_frame",
    "step_3_roihu_video", "step_4_roihu_summary", "step_5_roihu_postprocess",
    "step_6_roihu_discourse_analysis", "step_7_roihu_discourse_network_analysis",
    "step_8_roihu_social_network_analysis", "step_9_roihu_rdf",
)

EP24_LEGACY_STAGES = (
    "puhti_preprocess", "puhti_frame", "puhti_summary", "puhti_populism", "puhti_postprocess",
)


def _snapshot_ref(pipeline_id: str) -> tuple[str, str]:
    """Read the pinned upstream SHA from the vendored provenance, never from a branch."""
    path = PACKAGE_DIR / pipeline_id.replace("-", "_") / "PROVENANCE.json"
    if not path.is_file():
        return "", ""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("source_ref", ""), data.get("source_repository", "")


_ep24_ref, _ep24_repo = _snapshot_ref("ep24")
_legacy_ref, _legacy_repo = _snapshot_ref("ep24-legacy")

REGISTRY: dict[str, PipelineSpec] = {
    "ai26": PipelineSpec(
        pipeline_id="ai26",
        version="1",
        display_name="AI26 canonical stages",
        stages=AI26_STAGES,
        stage_prefix="stage:",
        notes=(
            "The production pipeline. Behaviour is unchanged by the multi-pipeline "
            "introduction; the Laskin realtime runner keeps its CLI and env contract."
        ),
    ),
    "ep24": PipelineSpec(
        pipeline_id="ep24",
        version=_ep24_ref[:12] or "unpinned",
        display_name="EP24 current (Roihu Step 0-9)",
        stages=EP24_STAGES,
        stage_prefix="step_",
        entry_module="ep24_pipeline",
        snapshot_dir="ep24",
        source_repository=_ep24_repo or "TomiToivio/LaclauGPT-Multimodal-Analysis",
        source_ref=_ep24_ref,
        requires=("pandas",),
        notes=(
            "Vendored from upstream main at a pinned SHA. Modules are flat and import "
            "their siblings by bare name, so the snapshot's src/ directory is placed on "
            "sys.path when the pipeline is imported."
        ),
    ),
    "ep24-legacy": PipelineSpec(
        pipeline_id="ep24-legacy",
        version=_legacy_ref[:12] or "unpinned",
        display_name="EP24 legacy (Puhti era)",
        stages=EP24_LEGACY_STAGES,
        stage_prefix="puhti_",
        entry_module="puhti_preprocess",
        snapshot_dir="ep24_legacy",
        source_repository=_legacy_repo or "TomiToivio/LaclauGPT-Multimodal-Analysis",
        source_ref=_legacy_ref,
        requires=("cv2", "easyocr", "ollama", "pandas"),
        notes=(
            "The historical implementation, kept for reproducing its results, not for "
            "new analysis. It needs OpenCV and an Ollama client that the modern "
            "environment does not require; run it in the documented compatibility "
            "environment rather than adding those dependencies here."
        ),
    ),
}


def list_pipelines() -> list[PipelineSpec]:
    return [REGISTRY[k] for k in sorted(REGISTRY)]


def get_pipeline(pipeline_id: str) -> PipelineSpec:
    try:
        return REGISTRY[pipeline_id]
    except KeyError:
        known = ", ".join(sorted(REGISTRY))
        raise KeyError(f"unknown pipeline {pipeline_id!r}; registered: {known}") from None


def _missing(module_name: str) -> str | None:
    try:
        importlib.import_module(module_name)
        return None
    except Exception as exc:  # noqa: BLE001 - the message is the point
        return f"{type(exc).__name__}: {exc}"


def check_pipeline(pipeline_id: str) -> dict:
    """Report selectability without pretending a pipeline is runnable here.

    For a vendored pipeline the snapshot directory is put on ``sys.path`` first, because
    upstream's modules import their siblings by bare name. The path entry is removed
    afterwards so one pipeline's flat namespace cannot satisfy another's imports.
    """
    spec = get_pipeline(pipeline_id)
    report: dict = {
        "pipeline_id": spec.pipeline_id,
        "version": spec.version,
        "source_ref": spec.source_ref,
        "declared_stages": len(spec.stages),
        "missing_stages": [],
        "missing_requirements": [],
        "entry_module": spec.entry_module,
        "import_error": None,
        "selectable": True,
    }

    present = spec.stages_present()
    report["missing_stages"] = [s for s in spec.stages if s not in present]

    for requirement in spec.requires:
        problem = _missing(requirement)
        if problem:
            report["missing_requirements"].append({"module": requirement, "error": problem})

    if spec.entry_module:
        snapshot = spec.snapshot_path
        inserted = None
        if snapshot is not None and (snapshot / "src").is_dir():
            inserted = str(snapshot / "src")
            sys.path.insert(0, inserted)
        try:
            problem = _missing(spec.entry_module)
            report["import_error"] = problem
        finally:
            if inserted and inserted in sys.path:
                sys.path.remove(inserted)

    report["selectable"] = not report["missing_stages"] and report["import_error"] is None
    return report


def pipeline_namespace(pipeline_id: str, run_id: str) -> dict[str, str]:
    """Durable keys that keep two pipeline versions apart on the same input records.

    The pipeline id is part of the Redis stream, the consumer group and the Mongo result
    collections. Attaching it only as metadata would let two versions write into one
    result set and overwrite each other, which the issue explicitly forbids.
    """
    spec = get_pipeline(pipeline_id)
    prefix = f"analysis:{spec.pipeline_id}:{run_id}"
    return {
        "stream": f"{prefix}:tasks",
        "group": f"group:analysis:{spec.pipeline_id}:{run_id}",
        "dead_letter": f"{prefix}:dead",
        "result_collection": f"analysis_results__{spec.pipeline_id}",
        "failure_collection": f"analysis_failures__{spec.pipeline_id}",
    }


def snapshot_digest(pipeline_id: str) -> str:
    """SHA-256 over the vendored snapshot's recorded hashes.

    This is the fingerprint a run records, so "which EP24" has one answer rather than a
    directory listing.
    """
    spec = get_pipeline(pipeline_id)
    snapshot = spec.snapshot_path
    if snapshot is None:
        return ""
    provenance = snapshot / "PROVENANCE.json"
    if not provenance.is_file():
        return ""
    data = json.loads(provenance.read_text(encoding="utf-8"))
    hasher = hashlib.sha256()
    for path in sorted(data.get("files", {})):
        hasher.update(path.encode())
        hasher.update(data["files"][path]["sha256"].encode())
    return hasher.hexdigest()
