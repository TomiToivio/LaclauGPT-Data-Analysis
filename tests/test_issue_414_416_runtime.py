"""Integration regressions for #414/#416 after reconciling main's infrastructure retry policy."""
from __future__ import annotations

from pathlib import Path

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.distributed_worker import AI26TaskWorker
from laclaugpt_data_analysis.llm.base import TransientProviderError
from laclaugpt_data_analysis.task_queue import InMemoryTaskQueue, InMemoryTaskStore, TaskEnvelope


def _task(name: str, attempt: int = 1) -> TaskEnvelope:
    return TaskEnvelope(
        task_id=name, idempotency_key=name, project_id="ai26", run_id="run-001",
        task_type="analyze-record", record_ref=f"https://example.invalid/{name}",
        schema_version=SCHEMA_VERSION, config_revision="cfg",
        codebook_revision="cb", attempt=attempt,
    )


def test_exhausted_attempt_provider_outage_is_nonterminal():
    queue, store = InMemoryTaskQueue(), InMemoryTaskStore()
    queue.publish(_task("outage-1", attempt=3))
    worker = AI26TaskWorker(
        queue=queue, durable_store=store,
        handler=lambda _: (_ for _ in ()).throw(TransientProviderError("HTTP 500")),
        worker_id="test", provenance={}, max_attempts=3,
    )
    assert worker.run_once() == "retry"
    assert queue.pending[-1].task.attempt == 3
    assert queue.dead_letters == []
    assert not store.has_terminal_failure("outage-1")
    assert store.failures[-1]["terminal"] is False
    assert store.failures[-1]["infrastructure"] is True


def test_requeued_provider_outage_can_recover_without_rearm():
    queue, store = InMemoryTaskQueue(), InMemoryTaskStore()
    queue.publish(_task("outage-2"))
    calls = 0

    def handler(_task):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TransientProviderError("HTTP 503")
        return {"ok": True}

    worker = AI26TaskWorker(
        queue=queue, durable_store=store, handler=handler,
        worker_id="test", provenance={}, max_attempts=3,
    )
    assert worker.run_once() == "retry"
    assert worker.run_once() == "completed"
    assert store.has_result("outage-2")
    assert not queue.claimed


def test_report_timeout_degraded_not_worker_failure_and_default_ceiling():
    script = (Path(__file__).resolve().parents[1] / "scripts" / "run_ai26_laskin.sh").read_text()
    assert 'REPORT_MAX_SECONDS=${LACLAUGPT_REPORT_MAX_SECONDS:-1800}' in script
    assert 'REPORT_STATUS" -eq 124 || "$REPORT_STATUS" -eq 137' in script
    degraded = script.split("REPORT_DEGRADED=1")[1].split("fi", 1)[0]
    assert "FINAL_STATUS=4" not in degraded
    assert "FINAL_STATUS=4" in script
