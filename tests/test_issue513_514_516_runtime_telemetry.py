"""#513/#514/#516: journal durability, Python compatibility, escalation semantics."""
from __future__ import annotations

import json
from pathlib import Path

from laclaugpt_data_analysis.ai26_tick_telemetry import append_tick


def test_python310_compatible_telemetry_writer():
    source = Path(__file__).resolve().parents[1] / "src/laclaugpt_data_analysis/ai26_tick_telemetry.py"
    assert "from datetime import UTC" not in source.read_text()


def test_check_only_writes_one_row_and_does_not_reset_skip_streak(tmp_path):
    journal = tmp_path / "ticks.jsonl"
    append_tick(journal, stage="lock", exit_code=3, check_only=False, skip_threshold=2)
    check = append_tick(journal, stage="check", exit_code=0, check_only=True, skip_threshold=2)
    second = append_tick(journal, stage="lock", exit_code=3, check_only=False, skip_threshold=2)
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    assert len(rows) == 3
    assert rows[1]["outcome"] == "check_ok"
    assert check["check_only"] is True
    assert second["skip_streak"] == 2
    assert second["escalation"] == "skipped"
    alert = json.loads((tmp_path / "ai26-analysis-alert.json").read_text())
    assert alert["escalation"] == "skipped"


def test_distinct_reject_streak_and_success_reset(tmp_path):
    journal = tmp_path / "ticks.jsonl"
    append_tick(journal, stage="preflight", exit_code=2, check_only=False, reject_threshold=2)
    rejected = append_tick(journal, stage="preflight", exit_code=2, check_only=False, reject_threshold=2)
    assert rejected["reject_streak"] == 2 and rejected["escalation"] == "rejected"
    append_tick(journal, stage="complete", exit_code=0, check_only=False, reject_threshold=2)
    new = append_tick(journal, stage="preflight", exit_code=2, check_only=False, reject_threshold=2)
    assert new["reject_streak"] == 1 and new["escalation"] is None


def test_nonzero_thresholds_opt_in(tmp_path):
    event = append_tick(tmp_path / "ticks.jsonl", stage="lock", exit_code=3, check_only=False)
    assert event["escalation"] is None


def test_wrapper_uses_one_exit_trap_and_venv(tmp_path):
    wrapper = (Path(__file__).resolve().parents[1] / "scripts/run_ai26_laskin.sh").read_text()
    assert 'trap record_tick_on_exit EXIT' in wrapper
    assert 'local interpreter="$ROOT_DIR/.venv/bin/python"' in wrapper
    assert 'tick_status already_running' not in wrapper
    assert 'TICK_STAGE="check"' in wrapper
