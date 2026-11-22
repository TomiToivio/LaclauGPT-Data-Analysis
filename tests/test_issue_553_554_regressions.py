"""Regression coverage for AI26 persistence and combined-stall alerts."""
from __future__ import annotations

from laclaugpt_data_analysis.ai26_tick_telemetry import append_tick
from laclaugpt_data_analysis.mongo_safety import strip_mongo_id


def test_mongo_boundary_removes_only_top_level_id():
    original = {"_id": "mongo-identity", "result": {"_id": "domain-identity"}, "value": 42}
    cleaned = strip_mongo_id(original)
    assert cleaned == {"result": {"_id": "domain-identity"}, "value": 42}
    assert original["_id"] == "mongo-identity"


def test_rejected_then_locked_escalates_without_reset(tmp_path):
    journal = tmp_path / "ticks.jsonl"
    kwargs = dict(check_only=False, skip_threshold=3, reject_threshold=2)
    first = append_tick(journal, stage="preflight", exit_code=2, **kwargs)
    second = append_tick(journal, stage="lock", exit_code=3, **kwargs)
    third = append_tick(journal, stage="lock", exit_code=3, **kwargs)
    assert first["escalation"] is None
    assert second["escalation"] == "stalled"
    assert second["reject_streak"] == 1
    assert third["stall_streak"] == 3
    assert third["escalation"] == "stalled"
    recovered = append_tick(journal, stage="complete", exit_code=0, **kwargs)
    assert recovered["escalation"] is None
    assert recovered["stall_streak"] == 0


def test_check_does_not_erase_rejection(tmp_path):
    journal = tmp_path / "ticks.jsonl"
    kwargs = dict(skip_threshold=3, reject_threshold=2)
    append_tick(journal, stage="preflight", exit_code=2, check_only=False, **kwargs)
    append_tick(journal, stage="check", exit_code=0, check_only=True, **kwargs)
    event = append_tick(journal, stage="preflight", exit_code=2, check_only=False, **kwargs)
    assert event["reject_streak"] == 2
    assert event["escalation"] == "stalled"
