"""#341: the logical-step dry-run is a transparent, non-executing contract view."""
from __future__ import annotations

import json

import pytest

from laclaugpt_data_analysis import ai26


@pytest.mark.parametrize("number", range(10))
def test_each_logical_step_is_inspectable_without_execution(number, capsys):
    result = ai26.main(["step", str(number), "--dry-run", "--json"])
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["logical_step"] == number
    assert payload["read_only"] is True
    assert payload["executed"] is False
    assert payload["claimed_tasks"] == 0
    if number == 3:
        # The issue's optional whole-video evidence. #341 requires it to be
        # machine-readable, so a stage is declared even though no module exists:
        # inspection must report the declared stage and say it has no module.
        assert [s["id"] for s in payload["stages"]] == ["video"]
        assert payload["stages"][0]["phase_status"] == "phase_1_optional_media"
        assert payload["stages"][0]["requires_media"] is True
        assert "no executable module" in payload["note"]
    else:
        assert payload["stages"]
    assert all("phase_status" in stage for stage in payload["stages"])


def test_text_only_summary_does_not_require_media(capsys):
    assert ai26.main(["step", "4", "--dry-run", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert all(not stage["requires_media"] for stage in payload["stages"])


@pytest.mark.parametrize("number", [7, 8])
def test_experimental_steps_are_clearly_labelled(number, capsys):
    assert ai26.main(["step", str(number), "--dry-run", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert all(stage["phase_status"] == "experimental_phase_2" for stage in payload["stages"])


def test_dry_run_is_mandatory():
    with pytest.raises(SystemExit) as exc:
        ai26.main(["step", "4"])
    assert exc.value.code == 2


def test_nonpositive_limit_rejected(capsys):
    assert ai26.main(["step", "4", "--dry-run", "--limit", "0"]) == 2
    assert "positive" in capsys.readouterr().err


def test_number_outside_registry_is_rejected():
    with pytest.raises(SystemExit) as exc:
        ai26.main(["step", "10", "--dry-run"])
    assert exc.value.code == 2


def test_a_declared_step_with_no_module_is_inspectable_and_says_so(capsys):
    """Step 3 is the issue's optional whole-video evidence: no module, still inspectable."""
    result = ai26.main(["step", "3", "--dry-run", "--json"])
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    # Declared, inspectable, and honest about the missing module.
    assert [s["id"] for s in payload["stages"]] == ["video"]
    assert payload["stages"][0]["module"] is None
    assert "no executable module" in payload["note"]


def test_a_step_outside_the_reading_order_is_rejected():
    """0-9 is the issue's reading order; anything else is refused before inspection."""
    with pytest.raises(SystemExit) as exc:
        ai26.main(["step", "42", "--dry-run", "--json"])
    assert exc.value.code == 2
