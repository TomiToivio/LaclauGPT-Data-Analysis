"""Offline registry contract; GitHub checkout may not initialize submodules."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/analysis_pipeline.py"

def test_pipeline_registry_lists_three_distinct_versions():
    result = subprocess.run([sys.executable, str(SCRIPT), "list"], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert set(data) == {"ai26", "ep24", "ep24-legacy"}
    assert len({data[k]["path"] for k in data}) == 3

def test_pinned_submodules_and_no_auto_science_fallback():
    config = (ROOT / ".gitmodules").read_text()
    assert "external/ep24-current" in config and "branch = main" in config
    assert "external/ep24-legacy" in config and "branch = legacy" in config
    source = SCRIPT.read_text()
    assert 'if ns.pipeline == "ai26"' in source
    assert "puhti_{ns.step}.py" in source
