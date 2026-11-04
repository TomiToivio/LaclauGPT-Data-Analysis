"""Regressions for #414 and #416: infrastructure failures are not document failures."""
from __future__ import annotations

from pathlib import Path

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.distributed_worker import AI26TaskWorker
from laclaugpt_data_analysis.llm.base import TransientProviderError
from laclaugpt_data_analysis.task_queue import InMemoryTaskQueue, InMemoryTaskStore, TaskEnvelope


def test_provider_outage_does_not_spend_attempt_or_dead_letter():
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    task = TaskEnvelope(
        task_id="outage-1", idempotency_key="outage-1", project_id="ai26",
        run_id="run-001", task_type="analyze-record",
        record_ref="https://example.invalid/1", schema_version=SCHEMA_VERSION,
        config_revision="cfg", codebook_revision="cb", attempt=3,
    )
    queue.publish(task)
    worker = AI26TaskWorker(
        queue=queue, durable_store=store,
        handler=lambda _: (_ for _ in ()).throw(TransientProviderError("HTTP 500")),
        worker_id="test", provenance={}, max_attempts=3,
    )
    assert worker.run_once() == "retry"
    assert queue.claimed["1"].task.attempt == 3
    assert queue.pending == []
    assert queue.dead_letters == []
    assert not store.has_terminal_failure("outage-1")
    assert store.failures[-1]["terminal"] is False


def test_reclaimed_provider_outage_task_can_complete_without_rearm():
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    task = TaskEnvelope(
        task_id="outage-2", idempotency_key="outage-2", project_id="ai26",
        run_id="run-001", task_type="analyze-record",
        record_ref="https://example.invalid/2", schema_version=SCHEMA_VERSION,
        config_revision="cfg", codebook_revision="cb",
    )
    queue.publish(task)
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
    assert worker.run_once(reclaim_idle_ms=0) == "completed"
    assert store.has_result("outage-2")
    assert not queue.claimed


def test_report_timeout_is_degraded_not_worker_failure():
    script = (Path(__file__).resolve().parents[1] / "scripts" / "run_ai26_laskin.sh").read_text()
    assert 'if [[ "$REPORT_STATUS" -eq 124 || "$REPORT_STATUS" -eq 137 ]]; then' in script
    timeout_branch = script.split('if [[ "$REPORT_STATUS" -eq 124 || "$REPORT_STATUS" -eq 137 ]]; then')[1].split("fi", 1)[0]
    assert "FINAL_STATUS=4" not in timeout_branch
    assert "reporting degraded: timeout" in timeout_branch
    assert "FINAL_STATUS=4" in script
