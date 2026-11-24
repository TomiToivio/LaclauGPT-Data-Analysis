"""The cycle wrapper runs the tick telemetry as a file, so the module must survive having no package.

The wrapper invokes ``python src/laclaugpt_data_analysis/ai26_tick_telemetry.py``. A relative import
in that position raises ``ImportError: attempted relative import with no known parent package``
before argparse ever runs, so the EXIT trap printed a warning and the tick journal went silent —
which is exactly when the journal matters, during a provider outage (#569).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def test_the_telemetry_writes_a_tick_when_run_as_a_file(tmp_path: Path) -> None:
    journal = tmp_path / "logs" / "ticks.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "laclaugpt_data_analysis.ai26_tick_telemetry",
            "--path",
            str(journal),
            "--stage",
            "complete",
            "--exit-code",
            "75",
            "--worker-status",
            "75",
            "--report-status",
            "not-run",
            "--git-sha",
            "deadbee",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(SRC)},
    )
    assert result.returncode == 0, result.stderr
    assert "ImportError" not in result.stderr
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["exit_code"] == 75
    assert rows[0]["outcome"] == "provider_unavailable", rows[0]


def test_the_capacity_outcome_still_matches_the_wrapper_exit_code() -> None:
    """Exit 75 is the wrapper's contract; the journal has to name it as capacity, not failure."""
    from laclaugpt_data_analysis.provider_capacity import (
        CAPACITY_OUTCOME,
        EXIT_PROVIDER_UNAVAILABLE,
    )

    assert EXIT_PROVIDER_UNAVAILABLE == 75
    assert CAPACITY_OUTCOME == "provider_unavailable"
