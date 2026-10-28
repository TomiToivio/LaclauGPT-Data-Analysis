"""Multi-pipeline registry and namespace separation (#399).

Two properties are load-bearing and both are cheap to break:

1. **Explicit selection.** A typo must fail, not fall back to whatever pipeline happens to be first.
2. **Separated execution.** EP24 and EP24-legacy may analyse the same frozen record; their queues,
   leases, result collections and artifact prefixes must still be distinct, or one version silently
   completes the other's work and the comparison is meaningless.

The imports themselves are checked too: a snapshot that cannot be imported is not an imported
pipeline, and the failure should surface in CI rather than during a research run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from laclaugpt_data_analysis.pipelines import (
    PIPELINES,
    UnknownPipeline,
    get_pipeline,
    list_pipelines,
    pipeline_keys,
)

ROOT = Path(__file__).resolve().parents[1]
PIPELINES_DIR = ROOT / "src" / "laclaugpt_data_analysis" / "pipelines"
INVENTORY = ROOT / "docs" / "EP24_SOURCE_INVENTORY.json"


def test_registry_exposes_the_three_required_pipelines():
    assert {"ai26", "ep24", "ep24-legacy"} <= set(PIPELINES)
    assert [spec.pipeline_id for spec in list_pipelines()] == sorted(PIPELINES)


def test_unknown_pipeline_is_refused_instead_of_defaulted():
    with pytest.raises(UnknownPipeline):
        get_pipeline("ep25")
    with pytest.raises(UnknownPipeline):
        get_pipeline("")


def test_each_pipeline_declares_its_source():
    for spec in list_pipelines():
        assert spec.source_repository, spec.pipeline_id
        assert spec.source_sha, spec.pipeline_id
        assert spec.stages, spec.pipeline_id


def test_ep24_pipelines_are_not_aliases_of_ai26():
    """A stub would be the easy failure mode this test exists to prevent."""
    for pipeline_id in ("ep24", "ep24-legacy"):
        spec = get_pipeline(pipeline_id)
        assert spec.package != get_pipeline("ai26").package
        assert tuple(spec.stages) != tuple(get_pipeline("ai26").stages)


def test_legacy_stage_names_are_historical():
    legacy = get_pipeline("ep24-legacy")
    assert tuple(legacy.stages) == ("preprocess", "frame", "summary", "populism", "postprocess")


def test_namespaces_separate_pipeline_versions_even_for_the_same_run_id():
    common = {"project_id": "ep24", "run_id": "sample-001"}
    ai26 = pipeline_keys(pipeline_id="ai26", **common)
    current = pipeline_keys(pipeline_id="ep24", **common)
    legacy = pipeline_keys(pipeline_id="ep24-legacy", **common)

    for key in ("redis_stream", "redis_group", "redis_dead_letter", "redis_worker_key", "mongo_results", "s3_prefix"):
        values = {ai26[key], current[key], legacy[key]}
        assert len(values) == 3, f"{key} collides: {values}"


def test_namespaces_separate_runs_of_the_same_pipeline():
    first = pipeline_keys(pipeline_id="ep24", project_id="ep24", run_id="a")
    second = pipeline_keys(pipeline_id="ep24", project_id="ep24", run_id="b")
    assert first["redis_stream"] != second["redis_stream"]
    assert first["mongo_results"] == second["mongo_results"], (
        "results collections are per pipeline, so record identity must carry the run"
    )


def test_run_id_rejects_separator_injection():
    with pytest.raises(ValueError):
        pipeline_keys(pipeline_id="ep24", project_id="ep24", run_id="a:b")
    with pytest.raises(ValueError):
        pipeline_keys(pipeline_id="ep24", project_id="ep24", run_id="")


# --- snapshot fidelity -------------------------------------------------------------------------


def test_source_inventory_exists_and_matches_the_vendored_files():
    """The inventory is the contract: byte-identical import from a named commit."""
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    for pipeline_id, entry in inventory["pipelines"].items():
        assert len(entry["source_sha"]) == 40
        # pipeline ids are hyphenated for humans; package directories use underscores
        vendor = PIPELINES_DIR / pipeline_id.replace("-", "_") / "vendor"
        for row in entry["files"]:
            path = vendor / row["source_path"]
            assert path.is_file(), path
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == row["sha256"], f"{path} drifted from the recorded snapshot"


def test_every_snapshotted_ep24_stage_is_present():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    names = {row["source_path"] for row in inventory["pipelines"]["ep24"]["files"]}
    for step in range(10):
        assert any(name.startswith(f"step_{step}_") for name in names), f"missing step {step}"


def test_vendored_modules_are_syntactically_whole():
    """Compile, do not import.

    The upstream EP24 code is operational scripts: importing `puhti_populism` reads `ep24_fi.csv`,
    `puhti_summary` opens a SQLite file and several modules parse argv at module level. Executing
    them during a test run would be a side effect, not a check. Compiling proves the snapshot is
    intact and parseable under this interpreter without running the analysis.
    """
    total = 0
    for vendor in (PIPELINES_DIR / "ep24" / "vendor", PIPELINES_DIR / "ep24_legacy" / "vendor"):
        for path in sorted(vendor.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")  # raises on a corrupted snapshot
            total += 1
    assert total >= 40, f"expected the full snapshot, found {total} files"


def test_snapshot_scripts_have_module_level_execution():
    """Guard the finding above: if upstream ever becomes importable, this test tells us."""
    legacy = (PIPELINES_DIR / "ep24_legacy" / "vendor" / "puhti_populism.py").read_text(encoding="utf-8")
    # a top-level analysis loop: importing this file runs the pipeline
    assert "for country in countries:" in legacy
    guard = PIPELINES_DIR / "ep24_legacy" / "vendor" / "__init__.py"
    assert "Do not edit" in guard.read_text(encoding="utf-8")


def test_ai26_entrypoints_are_untouched_by_the_registry():
    """Backward compatibility: the production command still exists and points at the same module."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'laclaugpt-analysis-worker = "laclaugpt_data_analysis.contextual_entrypoints:worker_main"' in text
    assert 'laclaugpt-analysis = "laclaugpt_data_analysis.pipelines.cli:main"' in text


def test_cli_lists_pipelines(capsys):
    from laclaugpt_data_analysis.pipelines.cli import main

    assert main(["pipelines", "list"]) == 0
    out = capsys.readouterr().out
    for pipeline_id in ("ai26", "ep24", "ep24-legacy"):
        assert pipeline_id in out


def test_cli_refuses_unknown_pipeline(capsys):
    from laclaugpt_data_analysis.pipelines.cli import main

    assert main(["pipelines", "show", "nope"]) == 2
    assert "unknown pipeline" in capsys.readouterr().err


def test_run_id_rejects_unsafe_namespace_segments():
    for run_id in ("../production", "..", ".", "a b", "a\\nb", "x\\t", "a\\\\b", "☃", "a" * 129):
        with pytest.raises(ValueError):
            pipeline_keys(pipeline_id="ep24", project_id="ep24", run_id=run_id)
    assert pipeline_keys(pipeline_id="ep24", project_id="ep24", run_id="roihu-test-001")["s3_prefix"].endswith("roihu-test-001")
