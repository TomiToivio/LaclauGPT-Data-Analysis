"""Issue #360: the periodic report must be bounded like the worker already is.

The report runs after the worker and inside the same flock, so an unbounded report
does not fail the cycle — it starves the next one. These tests pin the ceiling, the
distinct status, and that the healthy path is untouched.
"""
from __future__ import annotations

import re
from pathlib import Path

WRAPPER = Path(__file__).resolve().parents[1] / "scripts" / "run_ai26_laskin.sh"


def wrapper() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def test_the_report_invocation_is_wrapped_in_a_wall_clock_ceiling() -> None:
    script = wrapper()
    report_pos = script.index("$REPORT_BIN")
    timeout_pos = script.rindex("timeout --signal=TERM", 0, report_pos)
    assert timeout_pos < report_pos, "the report is no longer inside its own ceiling (#360)"
    # Same process-group semantics as the worker watchdog, or a stuck report's
    # threads survive the signal and keep holding the lock.
    assert re.search(r"timeout --signal=TERM --kill-after=\"\$\{CYCLE_KILL_GRACE_SECONDS\}s\"", script)


def test_the_ceiling_is_configurable_from_the_environment() -> None:
    assert re.search(r"REPORT_MAX_SECONDS=\$\{LACLAUGPT_REPORT_MAX_SECONDS:-(\d+)\}", wrapper())


def test_an_invalid_ceiling_is_refused_before_any_work() -> None:
    script = wrapper()
    assert re.search(
        r'if \[\[ ! "\$REPORT_MAX_SECONDS" =~ \^\[1-9\]\[0-9\]\*\$ \]\]; then', script
    ), "a bad LACLAUGPT_REPORT_MAX_SECONDS must fail fast, not run unbounded"
    assert "ERROR: LACLAUGPT_REPORT_MAX_SECONDS must be a positive integer" in script


def test_the_default_ceiling_clears_the_observed_healthy_duration() -> None:
    """The measured healthy report duration is ~4 min; the ceiling must not clip it."""
    match = re.search(r"REPORT_MAX_SECONDS=\$\{LACLAUGPT_REPORT_MAX_SECONDS:-(\d+)\}", wrapper())
    assert match, "the report ceiling default is missing"
    default = int(match.group(1))
    assert default > 4 * 60, f"ceiling {default}s is inside the observed healthy report duration"
    assert default < 9000, "the report ceiling should be far below the worker cycle ceiling"


def test_a_breach_is_distinguishable_from_a_report_error() -> None:
    script = wrapper()
    assert re.search(r'\[\[\s*"\$REPORT_STATUS"\s*-eq\s*124', script)
    assert re.search(r'"\$REPORT_STATUS"\s*-eq\s*137', script)
    assert "periodic report CEILING exceeded" in script
    # A breach still flows into the existing report-failure path, so monitoring
    # keeps its worker-versus-report distinction.
    assert 'FINAL_STATUS=4' in script


def test_the_ceiling_is_announced_at_report_start() -> None:
    assert re.search(
        r"periodic report start run=\$LACLAUGPT_RUN_ID report_max_seconds=\$REPORT_MAX_SECONDS",
        wrapper(),
    )


def test_the_wrapper_documents_both_ceilings() -> None:
    script = wrapper()
    assert "LACLAUGPT_CYCLE_MAX_SECONDS (default 9000) bounds the worker" in script
    assert "LACLAUGPT_REPORT_MAX_SECONDS" in script


def test_it_is_a_syntax_valid_script() -> None:
    import subprocess

    completed = subprocess.run(["bash", "-n", str(WRAPPER)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
