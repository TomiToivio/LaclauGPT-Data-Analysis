"""#341: the documented operator entrypoints must be runnable exactly as documented."""
from __future__ import annotations

import stat
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Scripts whose own help text or the runbook invokes them by path, e.g.
#: ``scripts/ai26_run_next.sh --limit 1 --apply``. Committed as 100644 they raise
#: "Permission denied", so the documented command cannot be run at all.
OPERATOR_SCRIPTS = (
    "scripts/ai26_run_next.sh",
    "scripts/install_ai26_laskin_cron.sh",
    "scripts/run_ai26_laskin_analysis.sh",
)


@pytest.mark.parametrize("relative", OPERATOR_SCRIPTS)
def test_documented_operator_entrypoint_is_executable(relative):
    mode = (REPO_ROOT / relative).stat().st_mode
    assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH), (
        f"{relative} is not executable; the documented invocation fails with "
        "'Permission denied'"
    )
