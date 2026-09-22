"""Regression for issue #300: a length-exhausted document cannot poison each cycle."""
from __future__ import annotations

from pydantic import BaseModel

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.distributed_worker import AI26TaskWorker, seed_ready_tasks
from laclaugpt_data_analysis.llm.base import (
    ChatRequest, LLMCallProvenance, LLMResponse, LLMTruncationError,
)
from laclaugpt_data_analysis.llm.structured_output import chat_structured
from laclaugpt_data_analysis.task_queue import InMemoryTaskQueue, InMemoryTaskStore, TaskEnvelope


class Payload(BaseModel):
    value: str


class AlwaysLengthStopped:
    def __init__(self):
        self.budgets = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.budgets.append(request.options["num_predict"])
        return LLMResponse(
            content='{"value":"unfinished',
            provenance=LLMCallProvenance(
                requested_mode="local", requested_model="synthetic",
                resolved_model="synthetic", actual_mode="local",
                actual_model="synthetic",
            ),
            finish_reason="length",
            truncated=True,
        )


def task() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="analysis:over-budget", idempotency_key="over-budget",
        project_id="ai26", run_id="test-run", task_type="analyze-record",
        record_ref="https://example.invalid/synthetic", schema_version=SCHEMA_VERSION,
        config_revision="test-config", codebook_revision="test-codebook",
    )


def test_exhausted_output_is_terminal_queryable_and_does_not_reseed() -> None:
    provider = AlwaysLengthStopped()
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(task())

    def handler(_task: TaskEnvelope):
        # Uses the real structured-output escalation with a synthetic provider.
        chat_structured(
            provider, Payload, model="synthetic",
            system_prompt="system", user_prompt="input",
        )
        raise AssertionError("truncated JSON must never be accepted")

    worker = AI26TaskWorker(
        queue=queue, durable_store=store, handler=handler,
        worker_id="synthetic", provenance={}, max_attempts=3,
    )
    assert worker.run_once() == "dead-letter"
    assert provider.budgets == [4096, 8192]
    assert worker.last_failure_class == "LLMTruncationError"
    assert store.has_terminal_failure("over-budget")
    assert len(store.failures) == 1
    failure = store.failures[0]
    assert failure["terminal"] is True
    assert failure["terminal_reason"] == "unanalysable_within_budget"
    assert failure["finish_reason"] == "length"
    assert failure["output_budget_tokens"] == 8192
    assert failure["required_output_tokens_lower_bound"] == 8193
    assert failure["generated_output_chars"] == len('{"value":"unfinished')
    assert len(queue.dead_letters) == 1
    assert worker.run_once() == "idle"
    assert len(store.failures) == 1

    class Binding:
        manifest = type("Manifest", (), {"run_id": "test-run"})()

        @staticmethod
        def task_from_handoff(_handoff):
            return task()

    class Handoff:
        @staticmethod
        def ready_handoffs(_run_id, *, limit, offset=0):
            rows = [{"status": "ready", "run_id": "test-run",
                     "handoff_key": "over-budget",
                     "source_url": "https://example.invalid/synthetic"}]
            return rows[offset:offset + limit]

    next_queue = InMemoryTaskQueue()
    assert seed_ready_tasks(Binding(), Handoff(), next_queue, store, limit=1) == 0
    assert next_queue.pending == []
    assert len(store.failures) == 1
    assert store.rearm_terminal_failure("over-budget") == 1
    assert seed_ready_tasks(Binding(), Handoff(), next_queue, store, limit=1) == 1


def test_schema_errors_remain_distinct_and_retryable() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(task())
    worker = AI26TaskWorker(
        queue=queue, durable_store=store,
        handler=lambda _: (_ for _ in ()).throw(ValueError("schema mismatch")),
        worker_id="synthetic", provenance={}, max_attempts=3,
    )
    assert worker.run_once() == "retry"
    assert store.failures[0]["terminal"] is False
    assert "terminal_reason" not in store.failures[0]
