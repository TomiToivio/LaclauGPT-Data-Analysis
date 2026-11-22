"""Regressions for AI26 immutable Mongo identity and mixed stalled ticks."""
from __future__ import annotations

from laclaugpt_data_analysis.ai26_tick_telemetry import append_tick
from laclaugpt_data_analysis.storage import mongo_set_payload


def test_mongo_update_guard_removes_only_top_level_identity():
    row = {"_id": "mongo-object-id", "source_url": "https://example.test", "nested": {"_id": "data"}}
    payload = mongo_set_payload(row)
    assert payload == {"source_url": "https://example.test", "nested": {"_id": "data"}}
    assert "_id" in row  # caller's record is not mutated


def test_interleaved_preflight_and_lock_ticks_trigger_alert(tmp_path):
    path = tmp_path / "ticks.jsonl"
    one = append_tick(path, stage="preflight", exit_code=2, check_only=False,
                      reject_threshold=2, skip_threshold=3)
    two = append_tick(path, stage="lock", exit_code=3, check_only=False,
                      reject_threshold=2, skip_threshold=3)
    assert one["escalation"] is None
    assert two["stalled_streak"] == 2
    assert two["escalation"] == "stalled"
    assert two["reject_streak"] == 1
    assert two["skip_streak"] == 1


def test_success_clears_stalled_streak(tmp_path):
    path = tmp_path / "ticks.jsonl"
    append_tick(path, stage="preflight", exit_code=2, check_only=False,
                reject_threshold=2, skip_threshold=3)
    success = append_tick(path, stage="complete", exit_code=0, check_only=False,
                          reject_threshold=2, skip_threshold=3)
    assert success["stalled_streak"] == 0
    next_tick = append_tick(path, stage="lock", exit_code=3, check_only=False,
                            reject_threshold=2, skip_threshold=3)
    assert next_tick["stalled_streak"] == 1
    assert next_tick["escalation"] is None
