"""Multi-pipeline registry tests (#399).

The acceptance criteria ask for three things this file must be able to distinguish:

1. the registry exposes ``ai26``, ``ep24`` and ``ep24-legacy`` and is extensible;
2. both EP24 versions are **actually imported implementations**, not stubs or aliases
   of AI26 — so their stage modules must exist in the vendored snapshot and their
   provenance must name a real upstream commit;
3. the same input can be analysed by each pipeline without their durable keys colliding.

A registry test that only checks three names exist would pass for three empty packages.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from laclaugpt_data_analysis.pipelines import (
    REGISTRY,
    PipelineSpec,
    check_pipeline,
    get_pipeline,
    list_pipelines,
    pipeline_namespace,
    snapshot_digest,
)

ROOT = Path(__file__).resolve().parents[1]


def test_registry_exposes_the_three_required_identifiers():
    ids = [spec.pipeline_id for spec in list_pipelines()]
    assert ids == ["ai26", "ep24", "ep24-legacy"]


def test_registry_is_extensible():
    """A fourth pipeline must be addable without touching the lookup code."""
    original = dict(REGISTRY)
    try:
        REGISTRY["synthetic"] = PipelineSpec(
            pipeline_id="synthetic", version="0", display_name="synthetic",
            stages=("s1",), stage_prefix="s",
        )
        assert "synthetic" in [s.pipeline_id for s in list_pipelines()]
        assert get_pipeline("synthetic").stages == ("s1",)
    finally:
        REGISTRY.clear()
        REGISTRY.update(original)


def test_unknown_pipeline_is_refused_with_the_known_ones():
    with pytest.raises(KeyError) as exc:
        get_pipeline("ep24-v2")
    message = str(exc.value)
    assert "ep24-v2" in message
    assert "ai26" in message and "ep24-legacy" in message


def test_ai26_stage_declarations_match_the_real_stage_modules():
    """AI26 must not drift into the registry as a stale list of names."""
    spec = get_pipeline("ai26")
    stages_dir = ROOT / "src" / "laclaugpt_data_analysis" / "stages"
    present = {p.stem for p in stages_dir.glob("*.py")}
    assert set(spec.stages) <= present, set(spec.stages) - present


@pytest.mark.parametrize("pipeline_id,expected", [("ep24", 10), ("ep24-legacy", 5)])
def test_vendored_pipelines_ship_every_declared_stage(pipeline_id: str, expected: int):
    spec = get_pipeline(pipeline_id)
    assert len(spec.stages) == expected
    assert spec.stages_present() == list(spec.stages), "declared stage file is missing"


def test_ep24_is_an_imported_implementation_not_an_alias():
    """The current EP24 must be its own code, with a real upstream commit behind it."""
    spec = get_pipeline("ep24")
    assert spec.source_ref and len(spec.source_ref) == 40
    assert spec.entry_module == "ep24_pipeline"
    snapshot = spec.snapshot_path
    assert snapshot is not None and (snapshot / "src" / "ep24_pipeline.py").is_file()
    # Its stages are Roihu steps, not AI26 stage names.
    assert all(s.startswith("step_") for s in spec.stages)
    assert not set(spec.stages) & set(get_pipeline("ai26").stages)


def test_ep24_current_imports_and_is_selectable():
    report = check_pipeline("ep24")
    assert report["missing_stages"] == []
    assert report["import_error"] is None
    assert report["selectable"] is True


def test_ep24_legacy_reports_its_historical_dependencies_instead_of_lying():
    """Legacy is expected to be unrunnable in the modern environment — and to say so.

    Silently declaring it selectable would let a caller believe a historical run
    happened when nothing ran at all.
    """
    report = check_pipeline("ep24-legacy")
    assert report["missing_stages"] == []
    assert report["import_error"] is not None
    assert report["selectable"] is False
    assert get_pipeline("ep24-legacy").requires, "legacy dependencies must be declared"


@pytest.mark.parametrize("pipeline_id", ["ep24", "ep24-legacy"])
def test_vendored_files_match_their_recorded_hashes(pipeline_id: str):
    """Provenance is only worth recording if it is checked."""
    spec = get_pipeline(pipeline_id)
    snapshot = spec.snapshot_path
    assert snapshot is not None
    provenance = json.loads((snapshot / "PROVENANCE.json").read_text())
    assert provenance["source_ref"] == spec.source_ref
    checked = 0
    modified = set(provenance.get("local_modifications", []))
    for path, meta in provenance["files"].items():
        target = snapshot / meta["dest"]
        assert target.is_file(), f"vendored file missing: {path}"
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if path in modified:
            # A documented local change: the upstream hash is kept alongside it, so the
            # file is still traceable to what was imported and the reason is on record.
            assert meta.get("local_sha256") == digest, f"local change hash drifted: {path}"
            assert meta.get("upstream_sha256"), f"upstream hash lost: {path}"
            assert meta.get("local_changes"), f"local change undocumented: {path}"
        else:
            assert digest == meta["sha256"], f"vendored file changed: {path}"
        checked += 1
    assert checked == provenance["file_count"] > 0


def test_snapshot_digest_is_stable_and_distinct_per_pipeline():
    first = snapshot_digest("ep24")
    assert first == snapshot_digest("ep24")
    assert len(first) == 64
    assert first != snapshot_digest("ep24-legacy")
    assert snapshot_digest("ai26") == ""


def test_two_versions_on_one_run_id_get_different_durable_keys():
    """The same records and the same run id must not collide across versions."""
    ep24 = pipeline_namespace("ep24", "run-2026-01-01")
    legacy = pipeline_namespace("ep24-legacy", "run-2026-01-01")
    ai26 = pipeline_namespace("ai26", "run-2026-01-01")

    for key in ("stream", "group", "dead_letter", "result_collection", "failure_collection"):
        values = {ep24[key], legacy[key], ai26[key]}
        assert len(values) == 3, f"{key} collides between pipelines: {values}"


def test_namespace_carries_the_pipeline_id_and_run_id():
    ns = pipeline_namespace("ep24-legacy", "abc")
    assert "ep24-legacy" in ns["stream"]
    assert "abc" in ns["stream"]


def test_cli_lists_and_shows(capsys):
    from laclaugpt_data_analysis.pipelines.cli import main

    assert main(["list"]) == 0
    out = capsys.readouterr().out
    for expected in ("ai26", "ep24", "ep24-legacy"):
        assert expected in out

    assert main(["show", "ep24"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_ref"] == get_pipeline("ep24").source_ref
    assert len(payload["stages"]) == 10


def test_cli_check_strict_fails_for_legacy(capsys):
    from laclaugpt_data_analysis.pipelines.cli import main

    assert main(["check", "ep24", "--strict"]) == 0
    capsys.readouterr()
    assert main(["check", "ep24-legacy", "--strict"]) == 1


def test_vendor_tool_refuses_to_overwrite_a_snapshot(tmp_path: Path):
    """Re-importing over a snapshot destroys the reproduction it exists for."""
    source = tmp_path / "upstream"
    (source / "src").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.test"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=source, check=True)
    (source / "mod.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=source, check=True)
    ref = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source, capture_output=True,
                         text=True, check=True).stdout.strip()

    dest = tmp_path / "dest"
    tool = ROOT / "tools" / "vendor_pipeline.py"
    first = subprocess.run([sys.executable, str(tool), "--source", str(source), "--ref", ref,
                            "--dest", str(dest), "--pipeline-id", "synthetic"],
                           capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    assert (dest / "PROVENANCE.json").is_file()

    second = subprocess.run([sys.executable, str(tool), "--source", str(source), "--ref", ref,
                             "--dest", str(dest), "--pipeline-id", "synthetic"],
                            capture_output=True, text=True)
    assert second.returncode == 2
    assert "refusing to overwrite" in second.stderr
