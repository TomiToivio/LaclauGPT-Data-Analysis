import importlib

import pytest

pytest.importorskip("pandas", reason="vendored EP24 steps import pandas; it is an optional extra in CI")

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("step", [7, 8])
def test_vendor_retries_truncated_json(monkeypatch, step):
    root = Path(__file__).resolve().parents[1] / "src/laclaugpt_data_analysis/pipelines/ep24"
    monkeypatch.syspath_prepend(str(root / "src"))
    monkeypatch.syspath_prepend(str(root / "vendor"))
    name = next((root / "vendor").glob(f"step_{step}_*.py")).stem
    module = importlib.import_module(name)
    model = Mock()
    monkeypatch.setitem(sys.modules, "ollama", model)
    bad = {"message": {"content": '{"analysis_markdown":'}, "done_reason": "length"}
    field = "statements" if step == 7 else "edges"
    good = {"message": {"content": '{"analysis_markdown":"brief","' + field + '":[]}'}}
    model.chat.side_effect = [bad, good]
    if step == 7:
        monkeypatch.setattr(module, "_model_metadata", lambda: {"model": "test", "num_ctx": 8192, "num_predict": 2048})
        def extract():
            return module.analyze_context("synthetic evidence")[1]
    else:
        def extract():
            return module.analyze_context(model, "test", "synthetic evidence", module._models()[0])
    assert extract().analysis_markdown == "brief"
    calls = model.chat.call_args_list
    assert [call.kwargs["options"]["num_predict"] for call in calls] == [2048, 4096]
    assert all(call.kwargs["think"] is False for call in calls)
    model.chat.side_effect = [bad] * 3
    with pytest.raises(Exception, match="truncated before the JSON closed"):
        extract()


@pytest.mark.parametrize("step", [7, 8])
def test_selective_vendor_prompts_are_versioned_and_retry_instructions_fingerprinted(monkeypatch, step):
    root = Path(__file__).resolve().parents[1] / "src/laclaugpt_data_analysis/pipelines/ep24"
    monkeypatch.syspath_prepend(str(root / "src"))
    monkeypatch.syspath_prepend(str(root / "vendor"))
    name = next((root / "vendor").glob(f"step_{step}_*.py")).stem
    module = importlib.import_module(name)
    assert ("v4-" if step == 7 else "/3.2-") in module.PROMPT_VERSION
    first = module._extraction_system_prompt(0) if step == 7 else module._extraction_prompt(0)
    retry = module._extraction_system_prompt(1) if step == 7 else module._extraction_prompt(1)
    assert "600 characters" in first
    assert "250 characters" in retry
    assert first != retry


def test_step7_resume_fingerprint_covers_both_instructions_and_generation_settings(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "src/laclaugpt_data_analysis/pipelines/ep24"
    monkeypatch.syspath_prepend(str(root / "src"))
    monkeypatch.syspath_prepend(str(root / "vendor"))
    module = importlib.import_module("step_7_roihu_discourse_network_analysis")
    monkeypatch.setattr(module, "_model_metadata", lambda: {
        "model": "synthetic", "num_ctx": 8192, "num_predict": 2048, "temperature": 0.0,
    })
    original = module._prompt_hash("synthetic evidence")
    monkeypatch.setattr(module, "_extraction_system_prompt", lambda attempt: f"changed-{attempt}")
    assert module._prompt_hash("synthetic evidence") != original
    monkeypatch.setattr(module, "_model_metadata", lambda: {
        "model": "synthetic", "num_ctx": 8192, "num_predict": 4096, "temperature": 0.0,
    })
    assert module._prompt_hash("synthetic evidence") != original
