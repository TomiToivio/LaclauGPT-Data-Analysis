"""Issue #569: the parked capacity status must be visible to the operator."""

from __future__ import annotations

from pathlib import Path

from laclaugpt_data_analysis.distributed_worker import _cycle_exit_code


def test_provider_capacity_park_has_a_distinct_named_exit_code() -> None:
    assert _cycle_exit_code({"provider_unavailable": 1, "retry": 2}) == 75


def test_wrapper_names_the_capacity_park_and_documents_exit_75() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "run_ai26_laskin.sh").read_text(encoding="utf-8")
    docs = (root / "docs" / "AI26_LASKIN_ANALYSIS.md").read_text(encoding="utf-8")

    assert '"$WORKER_STATUS" -eq 75' in script
    assert "PROVIDER CAPACITY UNAVAILABLE" in script
    assert "no GPU capacity" in script
    assert "#569" in script
    assert "\n75  provider capacity unavailable" in docs
    assert "#569" in docs
