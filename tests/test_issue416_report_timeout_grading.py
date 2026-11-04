"""Issue #416: a lost periodic report must not grade a healthy worker cycle as failed.

Measured on Laskin: five ceiling breaches in fourteen hours, each ending
``report_status=124 status=4`` even though the worker in that cycle had completed normally.
Nothing in the authoritative ``analysis end`` line distinguished "the report is slow" from
"the pipeline is broken".

These tests pin the two halves of the fix:

* the ceiling breach is reported as ``report_status=timeout`` and no longer flips the cycle to
  the report-failure exit code;
* a genuine report error still does (the worker-versus-report distinction that #360 created
  stays intact);
* the default ceiling clears the observed healthy duration with headroom instead of clipping it.
"""
from __future__ import annotations

import re
from pathlib import Path

WRAPPER = Path(__file__).resolve().parents[1] / "scripts" / "run_ai26_laskin.sh"


def script() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def test_a_ceiling_breach_is_named_as_a_timeout() -> None:
    body = script()
    assert 'REPORT_STATUS="timeout"' in body, "a breach must be distinguishable from a report error"
    match = re.search(r'if \[\[ "\$REPORT_STATUS" -eq 124 \|\| "\$REPORT_STATUS" -eq 137 \]\]; then', body)
    assert match, "the timeout branch no longer covers both TERM and KILL escalations"


def test_a_ceiling_breach_no_longer_fails_the_cycle() -> None:
    body = script()
    timeout_branch = body[body.index('REPORT_STATUS="timeout"') :]
    timeout_branch = timeout_branch[: timeout_branch.index("elif [[")] if "elif [[" in timeout_branch else timeout_branch
    assert "FINAL_STATUS=4" not in timeout_branch, (
        "a lost report must not mark a healthy worker cycle as failed (#416)"
    )


def test_a_real_report_error_still_fails_the_cycle() -> None:
    body = script()
    assert 'elif [[ "$REPORT_STATUS" -ne 0 ]]; then' in body
    error_branch = body[body.index('elif [[ "$REPORT_STATUS" -ne 0 ]]; then'):]
    error_branch = error_branch[: error_branch.index("FINAL_STATUS=4") + len("FINAL_STATUS=4")]
    assert "FINAL_STATUS=4" in error_branch


def test_the_end_line_still_reports_worker_and_report_separately() -> None:
    body = script()
    assert 'log "AI26 Laskin analysis end worker_status=$WORKER_STATUS report_status=$REPORT_STATUS status=$FINAL_STATUS"' in body


def test_the_default_ceiling_clears_the_observed_worst_case() -> None:
    """The measured healthy report took 9-15 minutes; the old 900 s default sat on the edge."""
    match = re.search(r"REPORT_MAX_SECONDS=\$\{LACLAUGPT_REPORT_MAX_SECONDS:-(\d+)\}", script())
    assert match, "the report ceiling default is missing"
    default = int(match.group(1))
    assert default >= 15 * 60, f"ceiling {default}s does not clear the observed 15-minute report"
    assert default < 9000, "the report ceiling must stay far below the worker cycle ceiling"


def test_the_breach_line_states_that_the_worker_was_healthy() -> None:
    body = script()
    breach = [line for line in body.splitlines() if "report_status=timeout" in line]
    assert breach, "no log line announces the timeout grading"
    assert any("worker healthy" in line for line in breach), (
        "the line must say the worker succeeded, or the reader still cannot tell the two apart"
    )
