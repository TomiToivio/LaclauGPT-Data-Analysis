"""Offline guards for cross-version comparison (#399)."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_ep24_manifests.py"
spec = importlib.util.spec_from_file_location("compare_ep24_manifests", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def manifest(pipeline, run, ids=("same-input",)):
    return {
        "pipeline_id": pipeline,
        "run_id": run,
        "input_ids": list(ids),
        "stage_statuses": {"preprocess": "completed"},
        "upstream_sha": "f" * 40,
    }


def test_comparable_manifest_preserves_distinct_runs():
    result = module.compare(
        manifest("ep24", "ep24-test-1"),
        manifest("ep24-legacy", "legacy-test-1"),
    )
    assert result["input_count"] == 1
    assert result["runs"]["ep24"]["run_id"] != result["runs"]["ep24-legacy"]["run_id"]


def test_mismatched_inputs_rejected():
    with pytest.raises(ValueError, match="Input sets differ"):
        module.compare(
            manifest("ep24", "current", ("a",)),
            manifest("ep24-legacy", "legacy", ("b",)),
        )


def test_shared_run_identity_rejected():
    with pytest.raises(ValueError, match="Run identities"):
        module.compare(manifest("ep24", "same"), manifest("ep24-legacy", "same"))


def test_wrong_pipeline_and_duplicate_ids_rejected(tmp_path):
    import json

    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps(manifest("ai26", "run")))
    with pytest.raises(ValueError, match="expected pipeline"):
        module.read(wrong, "ep24")

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(json.dumps(manifest("ep24", "run", ("a", "a"))))
    with pytest.raises(ValueError, match="duplicate input"):
        module.read(duplicate, "ep24")
