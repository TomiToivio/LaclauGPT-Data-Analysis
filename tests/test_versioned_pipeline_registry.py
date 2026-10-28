"""Registry contract: three distinct versions, and no automatic fallback (#399).

This test replaced a submodule-based version of itself. Git submodules pinned to a branch
are a runtime dependency on a mutable ref — the issue asks for a controlled snapshot with
an explicit sync policy instead — and a checkout without `--recursive` would have made the
registry report three pipelines while shipping zero implementations.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "laclaugpt_data_analysis.pipelines.cli", *args],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_pipeline_registry_lists_three_distinct_versions():
    data = json.loads(_run("list", "--json"))
    assert {entry["pipeline_id"] for entry in data} == {"ai26", "ep24", "ep24-legacy"}
    # Distinct implementations, not three names for one: each has its own stage set and
    # its own pinned source revision.
    stages = {entry["pipeline_id"]: json.loads(_run("show", entry["pipeline_id"]))["stages"]
              for entry in data}
    refs = {entry["pipeline_id"]: entry["source_ref"] for entry in data}
    assert len({tuple(v) for v in stages.values()}) == 3
    assert refs["ep24"] and refs["ep24-legacy"]
    assert refs["ep24"] != refs["ep24-legacy"]


def test_no_automatic_fallback_to_another_pipeline():
    result = subprocess.run(
        [sys.executable, "-m", "laclaugpt_data_analysis.pipelines.cli", "show", "ep24-v2"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 2
    assert "ep24-v2" in result.stderr
    assert "ep24-legacy" in result.stderr, "the error must list what is registered"


def test_pipelines_are_vendored_not_submodules():
    """A submodule checkout without --recursive would leave the registry listing
    implementations that are not present; vendored snapshots cannot be absent."""
    assert not (ROOT / ".gitmodules").exists()
    from laclaugpt_data_analysis.pipelines import get_pipeline

    for pipeline_id in ("ep24", "ep24-legacy"):
        snapshot = get_pipeline(pipeline_id).snapshot_path
        assert snapshot is not None and snapshot.is_dir()
        assert (snapshot / "PROVENANCE.json").is_file()


@pytest.mark.parametrize("pipeline_id", ["ep24", "ep24-legacy"])
def test_source_ref_is_a_pinned_commit_not_a_branch(pipeline_id: str):
    from laclaugpt_data_analysis.pipelines import snapshot_digest

    spec = __import__("laclaugpt_data_analysis.pipelines", fromlist=["get_pipeline"]).get_pipeline(
        pipeline_id
    )
    assert len(spec.source_ref) == 40, "source_ref must be a commit SHA, not a branch name"
    assert len(snapshot_digest(pipeline_id)) == 64
