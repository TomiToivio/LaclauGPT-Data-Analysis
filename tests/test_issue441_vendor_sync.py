"""Issue #441: the vendored EP24 step modules must not silently drift from upstream.

A vendored copy that lags its source of truth is how a fixed defect returns: the truncation guards
were merged upstream while this repository's copy still called the model once with no budget and no
retry. These checks assert the *guards*, not a checksum, so a formatting change does not fail the
suite while a missing safeguard does.
"""
from __future__ import annotations

import json
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / "src" / "laclaugpt_data_analysis" / "pipelines" / "ep24" / "vendor"


def _source(name: str) -> str:
    return (VENDOR / name).read_text(encoding="utf-8")


class TestStep7Guards:
    def test_step7_retries_with_a_growing_budget(self):
        source = _source("step_7_roihu_discourse_network_analysis.py")
        assert "num_predict = metadata[\"num_predict\"] * (2 ** attempt)" in source
        assert "LACLAUGPT_STEP7_PARSE_ATTEMPTS" in source

    def test_step7_disables_thinking_for_structured_output(self):
        assert "think=False" in _source("step_7_roihu_discourse_network_analysis.py")

    def test_step7_bounds_the_analysis_text(self):
        source = _source("step_7_roihu_discourse_network_analysis.py")
        assert "OUTPUT BUDGET" in source, "#403 bounded the JSON-visible analysis text"

    def test_step7_names_truncation_in_the_stored_error(self):
        assert "truncated before the JSON closed" in _source(
            "step_7_roihu_discourse_network_analysis.py")


class TestStep8Guards:
    def test_step8_has_a_retry_loop_and_a_budget(self):
        source = _source("step_8_roihu_social_network_analysis.py")
        assert "def extract_with_retries(" in source
        assert "LACLAUGPT_STEP8_NUM_PREDICT" in source
        assert "LACLAUGPT_STEP8_PARSE_ATTEMPTS" in source

    def test_step8_clears_stale_output_before_retrying(self):
        assert "clear_step8_output(" in _source("step_8_roihu_social_network_analysis.py")

    def test_step8_disables_thinking(self):
        assert "think=False" in _source("step_8_roihu_social_network_analysis.py")


class TestVendorProvenance:
    def test_provenance_records_the_upstream_commit(self):
        record = json.loads((VENDOR / "PROVENANCE.json").read_text(encoding="utf-8"))
        sync = record.get("step7_step8_synced_from") or {}
        assert len(str(sync.get("commit") or "")) >= 7, "the upstream commit must be recorded"
        assert "step_7_roihu_discourse_network_analysis.py" in (sync.get("files") or [])
