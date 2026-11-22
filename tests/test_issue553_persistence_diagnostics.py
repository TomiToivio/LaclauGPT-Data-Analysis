"""#553: a persistence failure must name the failing site without leaking its content.

Locating the Mongo code-66 bug took a manual re-run and grep because the log carried only the
exception class and code. Printing the traceback is not available as a fix: exception text can
carry private source material (see the #515 note in the worker). Frame names carry no content, so
the log now reports ``site=module.py:line:function`` and nothing else.
"""

from __future__ import annotations

import logging

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.distributed_worker import AI26TaskWorker, _persistence_site
from laclaugpt_data_analysis.task_queue import InMemoryTaskQueue, InMemoryTaskStore, TaskEnvelope

PRIVATE = "PRIVATE-SOURCE-SENTENCE-THAT-MUST-NEVER-BE-LOGGED"


def _task() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task-1",
        idempotency_key="id-1",
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref="https://example.invalid/source/1",
        schema_version=SCHEMA_VERSION,
        config_revision="cfg",
        codebook_revision="cb",
    )


class _FailingWriteStore(InMemoryTaskStore):
    """A store whose persist step fails the way MongoDB does, with private text in the message."""

    def write_result(self, task, result, provenance, *, fingerprint=""):
        raise RuntimeError(f"write rejected while storing: {PRIVATE}")


def test_persistence_failure_log_names_the_site_and_not_the_content(caplog):
    queue = InMemoryTaskQueue()
    queue.publish(_task())
    worker = AI26TaskWorker(
        queue=queue,
        durable_store=_FailingWriteStore(),
        handler=lambda task: {"task_id": task.task_id, "attempt": task.attempt},
        worker_id="worker-1",
        provenance={},
        max_attempts=1,
    )

    with caplog.at_level(logging.ERROR):
        outcome = worker.run_once()

    # The worker absorbs the failure; it does not escape run_once. With the retry budget spent
    # (max_attempts=1) the task is dead-lettered rather than requeued.
    assert outcome == "dead-letter"

    line = "\n".join(record.getMessage() for record in caplog.records)
    assert "operation=write_result" in line
    assert "site=" in line
    # The site is a frame chain: file:line:function
    site = line.split("site=", 1)[1].split(";", 1)[0]
    assert ".py:" in site
    assert ":" in site.rsplit(".py:", 1)[1]
    # ...and the private content of the failure never reaches the log.
    assert PRIVATE not in line


def test_persistence_site_reports_the_innermost_frames_only():
    def inner():
        raise ValueError("boom")

    def outer():
        inner()

    try:
        outer()
    except ValueError as exc:
        site = _persistence_site(exc)

    parts = site.split("<-")
    assert len(parts) <= 3
    assert parts[-1].endswith(":inner"), site
    assert all(".py:" in part for part in parts)


def test_persistence_site_survives_an_exception_without_a_traceback():
    """A re-raised or synthesised exception has no frames; the log must still be well-formed."""
    assert _persistence_site(RuntimeError("no traceback here")) == ""
