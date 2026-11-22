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
