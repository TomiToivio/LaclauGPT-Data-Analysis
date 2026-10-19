"""Issue #341: offline stage-registry and prompt reference validation."""
from __future__ import annotations

import copy
import json

from laclaugpt_data_analysis import ai26


def test_shipped_registry_is_self_consistent(capsys):
    assert ai26.main(["validate-contract", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is True
    assert report["read_only"] is True
    assert report["errors"] == []


def test_validation_detects_phase_drift_and_missing_prompt():
    registry = copy.deepcopy(ai26.load_stage_registry())
    registry["phase_2_stages"][0]["in_canonical_list"] = True
    registry["canonical_stages"][2]["prompt_stage"] = "unknown_method"
    errors = ai26.validate_stage_registry(registry)
    assert any("Phase 2 cannot be a canonical prerequisite" in e for e in errors)
    assert any("unmapped AI26 prompt stage" in e for e in errors)


def test_validation_detects_unsafe_media_and_duplicate_id():
    registry = copy.deepcopy(ai26.load_stage_registry())
    registry["canonical_stages"][2]["conditional"] = False
    registry["canonical_stages"][1]["id"] = "handoff"
    errors = ai26.validate_stage_registry(registry)
    assert any("media requirement must be conditional" in e for e in errors)
    assert any("duplicate stage id" in e for e in errors)


def test_failed_validation_has_nonzero_exit_code(monkeypatch, capsys):
    registry = copy.deepcopy(ai26.load_stage_registry())
    registry["phase_2_stages"][0]["phase_status"] = "phase_1"
    monkeypatch.setattr(ai26, "load_stage_registry", lambda: registry)
    assert ai26.main(["validate-contract", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["valid"] is False
