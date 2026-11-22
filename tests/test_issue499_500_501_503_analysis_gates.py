"""#499 / #500 / #501 / #503 — the four ways the AI26 analysis stage lied about itself.

Found by testing the pipeline on Laskin on 2026-11-22, while it had analysed nothing for
three hours:

* #499/#500 the `--strict` deploy gate required *all three* sibling checkouts to match
  origin/main, so a routine merge in the dashboard repository stopped the paper's analysis.
  The failure also named no path and no remedy.
* #501 the object store refused every write (QuotaExceeded) while
  `object_store_required=false` let the run continue, and nothing in the run said so.
* #503 a tick that found the lock held exited 0, which is the same code a healthy tick exits.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from laclaugpt_data_analysis.deploy_drift import BEHIND, CURRENT, StrictVerdict, strict_verdict

ROOT = Path(__file__).resolve().parents[1]
OWNING = "LaclauGPT-Data-Analysis"
COLLECTION = "LaclauGPT-Data-Collection"
VISUALIZATION = "LaclauGPT-Data-Visualization"


def report(name: str, state: str = BEHIND, branch: str = "main", detail: str = "") -> dict:
    return {"name": name, "state": state, "branch": branch, "detail": detail}


def verdict(name: str, *, owning: bool = False, state: str = BEHIND) -> StrictVerdict:
    return strict_verdict(owning=owning, name=name, path=Path("/mnt/workspace") / name,
                          report=report(name, state=state))


# ------------------------------------------------------------------ #499 / #500

def test_the_owning_checkout_must_be_current():
    """The code doing the work is the one that has to match the reviewed revision."""
    assert verdict(OWNING, owning=True).blocks is True


def test_a_current_owning_checkout_blocks_nothing():
    assert verdict(OWNING, owning=True, state=CURRENT).blocks is False


def test_a_dashboard_checkout_can_never_stop_analysis():
    """#500: analysis does not read Visualization, so its merges must not halt the pipeline."""
    result = verdict(VISUALIZATION)
    assert result.blocks is False
    assert "cannot affect analysis" in result.warning


def test_record_source_drift_blocks_only_when_record_shape_moved(monkeypatch):
    monkeypatch.setattr(
        "laclaugpt_data_analysis.deploy_drift.analysis_blocking_changes",
        lambda path, reference="origin/main": ["src/laclaugpt_data_collection/models.py"],
    )
    result = verdict(COLLECTION)
    assert result.blocks is True
    assert "models.py" in result.remedy, "the remedy must name the file that moved"


def test_record_source_drift_without_schema_change_only_warns(monkeypatch):
    monkeypatch.setattr(
        "laclaugpt_data_analysis.deploy_drift.analysis_blocking_changes",
        lambda path, reference="origin/main": [],
    )
    result = verdict(COLLECTION)
    assert result.blocks is False
    assert "no record-shape file changed" in result.warning


def test_every_refusal_names_a_runnable_fix():
    """#500: the old line said only 'deployed revisions failed verification'."""
    result = verdict(OWNING, owning=True)
    assert "git -C" in result.remedy and "pull --ff-only" in result.remedy


# ------------------------------------------------------------------ #503

def test_a_lock_held_tick_reports_already_running():
    """#503: exit 0 made a starved tick indistinguishable from a healthy one."""
    script = (ROOT / "scripts" / "run_ai26_laskin_analysis.sh").read_text(encoding="utf-8")
    block = script[script.index("flock -n 9"):script.index("flock -n 9") + 400]
    assert "exit 3" in block
    assert "exit 0" not in block.replace("exiting with 3", "")


def test_the_wrapper_still_documents_the_code_it_now_returns():
    wrapper = (ROOT / "scripts" / "run_ai26_laskin.sh").read_text(encoding="utf-8")
    assert "3 already running" in wrapper


# ------------------------------------------------------------------ #501

def test_a_tolerated_object_store_failure_is_recorded_as_degraded(monkeypatch):
    """#501: `required: false` is an availability decision, not evidence that storage worked."""
    from laclaugpt_data_analysis import preflight

    monkeypatch.setenv("LACLAUGPT_OBJECT_STORE_REQUIRED", "0")
    monkeypatch.setattr(preflight, "_check_object_store", lambda settings: {
        "reachable": True, "writeable": False, "error_code": "QuotaExceeded", "blocking": True,
    })
    report_json = preflight.preflight_report()
    store = report_json["checks"]["object_store"]
    assert store["blocking"] is False, "the run is allowed to continue"
    assert store["degraded"] is True, "but the run must be able to say it was degraded"
    assert store["degraded_reason"] == "QuotaExceeded"


def test_a_healthy_object_store_is_not_degraded(monkeypatch):
    from laclaugpt_data_analysis import preflight

    monkeypatch.setenv("LACLAUGPT_OBJECT_STORE_REQUIRED", "0")
    monkeypatch.setattr(preflight, "_check_object_store", lambda settings: {
        "reachable": True, "writeable": True, "blocking": True,
    })
    assert "degraded" not in preflight.preflight_report()["checks"]["object_store"]


def test_the_cycle_status_line_carries_the_store_state():
    wrapper = (ROOT / "scripts" / "run_ai26_laskin.sh").read_text(encoding="utf-8")
    assert "object_store=$OBJECT_STORE_STATE" in wrapper, "the run record must carry it"
    assert "LACLAUGPT_OBJECT_STORE_REQUIRED=0 (recorded as degraded" in wrapper


def test_the_wrapper_is_still_valid_shell():
    result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "run_ai26_laskin.sh")],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
