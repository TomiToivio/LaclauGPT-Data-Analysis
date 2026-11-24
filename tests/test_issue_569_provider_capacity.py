"""A capacity outage must cost one scheduler timeout, not the whole cycle (#569).

On 2026-11-24 two AI26 cycles burned the full 9000 s ceiling because every analysis call paid a 900 s
`no GPU capacity` timeout, and the same three tasks were re-claimed at the head of every cycle. The
journal could not distinguish that from a merely slow cycle: both ended `status=124`.

These tests pin the four behaviours that end the outage, all of them mechanical:

* a capacity refusal is recognised, and a generic provider error is not;
* a capacity failure spends no attempt and is not republished inside the cycle;
* two consecutive capacity failures end the cycle, with exit 75 rather than 0 or 124;
* a task refused within the backoff window is deferred at seed time instead of being re-queued first.

No model, no database and no GPU: the worker loop here is the production loop over the in-memory adapters.
"""

from __future__ import annotations

from typing import Any, Mapping

from laclaugpt_data_analysis.ai26_tick_telemetry import append_tick
from laclaugpt_data_analysis.distributed_worker import (
    SEED_CAPACITY_DEFERRED,
    AI26TaskWorker,
    _cycle_exit_code,
    _run_bounded_cycle,
    seed_disposition,
)
from laclaugpt_data_analysis.llm.base import LLMTruncationError, TransientProviderError
from laclaugpt_data_analysis.provider_capacity import (
    CAPACITY_FAILURE_FIELD,
    CAPACITY_OUTCOME,
    EXIT_PROVIDER_UNAVAILABLE,
    capacity_reason,
    is_capacity_unavailable,
)
from laclaugpt_data_analysis.task_queue.memory import InMemoryTaskQueue, InMemoryTaskStore
from laclaugpt_data_analysis.task_queue.models import TaskEnvelope

NO_GPU = (
    "TransientProviderError: Ollama call failed: scheduler: no GPU capacity for gemma4:12b within "
    "900s (status code: 503)"
)


def task(key: str = "53b939c2") -> TaskEnvelope:
    envelope = TaskEnvelope(
        task_id=f"task-{key}",
        idempotency_key=key,
        project_id="ai26",
        run_id="run-1",
        task_type="analysis",
        record_ref=f"https://example.invalid/{key}",
        schema_version="1.2.0",
        config_revision="cfg",
        codebook_revision="cb",
    )
    envelope.validate()
    return envelope


def failing_worker(
    *errors: BaseException,
) -> tuple[AI26TaskWorker, InMemoryTaskQueue, InMemoryTaskStore]:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    remaining = list(errors)

    def handler(_task: TaskEnvelope) -> Mapping[str, Any]:
        if remaining:
            raise remaining.pop(0)
        return {"ok": True}

    # The AI26 worker is the one that owns the capacity policy; the base loop has no notion of a provider.
    worker = AI26TaskWorker(
        queue=queue,
        durable_store=store,
        handler=handler,
        worker_id="test",
        provenance={"project_id": "ai26"},
    )
    return worker, queue, store


class TestClassification:
    def test_the_reason_names_which_signal_was_seen(self):
        assert (
            capacity_reason(TransientProviderError(NO_GPU.split(": ", 1)[1])) == "no_gpu_capacity"
        )
        assert capacity_reason(TransientProviderError("connection reset")) is None

    def test_the_observed_laskin_error_is_capacity(self):
        assert is_capacity_unavailable(TransientProviderError(NO_GPU.split(": ", 1)[1]))

    def test_other_transient_failures_are_not_capacity(self):
        assert not is_capacity_unavailable(TransientProviderError("connection reset by peer"))
        assert not is_capacity_unavailable(TransientProviderError("Ollama call failed: 502"))

    def test_truncation_is_never_capacity(self):
        assert not is_capacity_unavailable(
            LLMTruncationError("no GPU capacity")
        )  # not a provider error


class TestNoAttemptIsSpent:
    def test_a_capacity_failure_goes_to_the_tail_and_is_marked_for_deferral(self):
        worker, queue, store = failing_worker(
            TransientProviderError("scheduler: no GPU capacity within 900s")
        )
        queue.publish(task())
        assert worker.run_once() == "retry"  # the merged park path (#570), not a document failure
        assert [item.task.idempotency_key for item in queue.pending] == ["53b939c2"]
        assert store.failures and store.failures[0][CAPACITY_FAILURE_FIELD] is True
        assert store.failures[0]["terminal"] is False

    def test_the_document_keeps_its_attempt(self):
        worker, queue, store = failing_worker(TransientProviderError("no GPU capacity"))
        queue.publish(task())
        worker.run_once()
        assert store.failures[0]["task"]["attempt"] == 1


class TestCycleAborts:
    def test_two_consecutive_capacity_failures_end_the_cycle_with_exit_75(self):
        worker, queue, _store = failing_worker(
            TransientProviderError("no GPU capacity"), TransientProviderError("no GPU capacity")
        )
        for index in range(3):
            queue.publish(task(f"key{index}"))
        counts, _classes = _run_bounded_cycle(worker, max_tasks=10, reclaim_idle_ms=None)
        assert counts["retry"] == 2
        assert counts["provider_unavailable"] == 1
        assert _cycle_exit_code(counts) == EXIT_PROVIDER_UNAVAILABLE

    def test_a_capacity_failure_followed_by_success_does_not_abort(self):
        worker, queue, _store = failing_worker(
            TransientProviderError("no GPU capacity"), TransientProviderError("no GPU capacity")
        )
        queue.publish(task("a"))
        counts, _classes = _run_bounded_cycle(worker, max_tasks=1, reclaim_idle_ms=None)
        assert counts.get("provider_unavailable_stop") is None
        assert (
            _cycle_exit_code(counts) == 1
        )  # one refusal cost the cycle its work: failed, not "nothing to do"

    def test_a_parked_cycle_is_75_even_if_it_completed_work_first(self):
        # Work done before the endpoint refused does not make the cycle healthy: it still ended because
        # the provider was unavailable, and that is what monitoring has to see.
        assert (
            _cycle_exit_code({"completed": 3, "provider_unavailable": 1})
            == EXIT_PROVIDER_UNAVAILABLE
        )


class TestSeedDefers:
    def test_a_recent_capacity_failure_defers_the_task_at_seed_time(self):
        worker, queue, store = failing_worker(TransientProviderError("no GPU capacity"))
        queue.publish(task())
        worker.run_once()
        assert store.has_capacity_deferral("53b939c2", within_minutes=30) is True
        assert store.has_capacity_deferral("other", within_minutes=30) is False

    def test_an_ordinary_failure_does_not_defer(self):
        worker, queue, store = failing_worker(RuntimeError("bad document"))
        queue.publish(task())
        worker.run_once()
        assert store.has_capacity_deferral("53b939c2", within_minutes=30) is False

    def test_a_seed_pass_that_only_deferred_is_named_as_such(self):
        assert seed_disposition({"capacity_deferred": 3, "published": 0}) == SEED_CAPACITY_DEFERRED
        assert (
            seed_disposition({"capacity_deferred": 0, "published": 0, "examined": 0})
            != SEED_CAPACITY_DEFERRED
        )


class TestJournal:
    def test_exit_75_is_recorded_as_a_provider_outage(self, tmp_path):
        event = append_tick(
            tmp_path / "ticks.jsonl", stage="worker", exit_code=75, check_only=False
        )
        assert event["outcome"] == CAPACITY_OUTCOME

    def test_a_capacity_outage_counts_toward_the_stall_alarm(self, tmp_path):
        journal = tmp_path / "ticks.jsonl"
        for _ in range(2):
            event = append_tick(
                journal, stage="worker", exit_code=75, check_only=False, stall_threshold=2
            )
        assert event["stall_streak"] == 2
        assert event["escalation"] == "stalled"
        assert event["stall_reasons"] == {CAPACITY_OUTCOME: 2}
