"""Guard for the AI26 worker cycle telemetry (issue #330).

The bounded worker reports its per-cycle counts and failure classes through the
``laclaugpt_data_analysis`` logger. Until #330 that telemetry was invisible:
nothing in the production path called ``configure_logging()``, so the logger
fell back to ``logging.lastResort`` (WARNING) and every ``logger.info`` record
was dropped. The cron log therefore showed only warnings -- the per-cycle
``completed`` / ``retry`` / ``dead-letter`` / ``failure_classes`` line never
appeared -- and the documented ``LACLAUGPT_DEBUG=1`` verbose mode was inert.

These are STRUCTURE guards, in the same spirit as the other issue guards here:
they check that the worker entrypoint installs the logging configuration, that
the documented debug flag reaches the logger level, and that the cycle summary
is still emitted at a level the installer keeps. They do not run the distributed
worker against a real queue.

Run: python -m pytest tests/test_issue_330_worker_cycle_telemetry.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER = "src/laclaugpt_data_analysis/distributed_worker.py"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_worker_main_installs_logging_before_running_a_cycle() -> None:
    """``main`` must configure logging at the entrypoint, not leave it to luck."""
    source = read(WORKER)
    assert "from .debug_mode import configure_logging" in source
    main_body = source.split("def main(", 1)[1]
    assert "configure_logging()" in main_body, (
        "distributed_worker.main must install the debug-mode logging handler so "
        "the per-cycle summary reaches stderr (issue #330)"
    )


def test_cycle_summary_is_emitted_through_the_logger() -> None:
    """The counts line the installer keeps must still be produced."""
    source = read(WORKER)
    assert "AI26 worker cycle: %s failure_classes=%s failure_summary=%s" in source


@pytest.fixture(autouse=True)
def _clean_logging_env(monkeypatch):
    monkeypatch.delenv("LACLAUGPT_DEBUG", raising=False)
    monkeypatch.setenv("LACLAUGPT_DEBUG", "")


def test_documented_debug_flag_reaches_the_logger_level(monkeypatch) -> None:
    """``LACLAUGPT_DEBUG=1`` must actually raise the level, as documented."""
    from laclaugpt_data_analysis import debug_mode

    root = logging.getLogger("laclaugpt_data_analysis")
    monkeypatch.setattr(root, "handlers", [], raising=False)
    monkeypatch.setenv("LACLAUGPT_DEBUG", "")
    assert debug_mode.configure_logging() == logging.INFO

    monkeypatch.setenv("LACLAUGPT_DEBUG", "1")
    assert debug_mode.configure_logging() == logging.DEBUG


def test_info_summary_is_not_dropped_after_configuration(monkeypatch) -> None:
    """With a handler installed, an INFO cycle summary is actually recorded."""
    from laclaugpt_data_analysis import debug_mode

    root = logging.getLogger("laclaugpt_data_analysis")
    monkeypatch.setattr(root, "handlers", [], raising=False)
    monkeypatch.setenv("LACLAUGPT_DEBUG", "")

    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    debug_mode.configure_logging(force=True)
    root.handlers[:] = [_Capture()]
    try:
        logging.getLogger("laclaugpt_data_analysis.distributed_worker").info(
            "AI26 worker cycle: %s failure_classes=%s failure_summary=%s",
            {"completed": 1},
            {},
            {},
        )
    finally:
        root.handlers[:] = []

    assert any("AI26 worker cycle:" in message for message in records)
