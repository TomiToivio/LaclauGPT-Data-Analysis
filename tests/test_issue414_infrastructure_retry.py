"""Issue #414: an upstream provider outage must not consume a document's retry budget.

The measured failure: a local Ollama 500 for four hours turned ten analysis tasks into
`terminal=true` quarantines, because ``ProviderError`` was neither truncation nor special-cased
and three 500s inside one outage exhausted ``max_attempts``.

What is pinned here:

* a provider 5xx / refused connection / timeout is typed ``ProviderUnavailable`` and is *not*
  a truncation;
* the worker refunds the attempt: the task returns to the queue at the same attempt number;
* the refund is bounded, so a provider that never comes back parks the document with an
  explicit reason instead of circulating forever;
* a content failure (validation, parse, generic runtime error) still consumes attempts and
  still reaches the dead-letter queue, because that is evidence about the document.
"""
from __future__ import annotations

import pytest

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.distributed_worker import AI26TaskWorker
from laclaugpt_data_analysis.llm.base import (
    LLMTruncationError,
    ProviderError,
    ProviderUnavailable,
)
from laclaugpt_data_analysis.task_queue import (
    InMemoryTaskQueue,
    InMemoryTaskStore,
    TaskEnvelope,
    infrastructure_failure,
)


def make_task() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task-414",
        idempotency_key="id-414",
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref="https://example.invalid/source/414",
        schema_version=SCHEMA_VERSION,
        config_revision="cfg",
        codebook_revision="cb",
    )


def make_worker(queue, store, handler, *, max_attempts: int = 3, refunds: int = 24):
    return AI26TaskWorker(
        queue=queue,
        durable_store=store,
        handler=handler,
        worker_id="worker-414",
        provenance={},
        max_attempts=max_attempts,
        max_infrastructure_refunds=refunds,
    )


def test_provider_unavailable_is_a_provider_error_but_not_a_truncation() -> None:
    assert issubclass(ProviderUnavailable, ProviderError)
    assert not issubclass(ProviderUnavailable, LLMTruncationError)
    assert infrastructure_failure(ProviderUnavailable("500"))
    assert not infrastructure_failure(LLMTruncationError("length"))
    assert not infrastructure_failure(ValueError("bad batch"))


def test_an_outage_does_not_consume_an_attempt() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(make_task())

    def outage(_task: TaskEnvelope):
        raise ProviderUnavailable("Ollama call failed: 500 Internal Server Error")

    worker = make_worker(queue, store, outage)

    assert worker.run_once() == "retry"
    assert len(queue.pending) == 1, "the task must return to the queue"
    assert queue.pending[0].task.attempt == 1, "a refunded attempt must not advance the counter"
    failure = store.failures[-1]
    assert failure["terminal"] is False
    assert failure.get("infrastructure") is True
    assert "500" in failure["error"]


def test_the_same_document_survives_a_long_outage_and_then_completes() -> None:
    """Ten 500s in a row must leave the attempt counter exactly where it started."""
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(make_task())
    attempts_seen: list[int] = []

    def flaky(task: TaskEnvelope):
        attempts_seen.append(task.attempt)
        if len(attempts_seen) <= 10:
            raise ProviderUnavailable("Ollama call failed: 500 Internal Server Error")
        return {"task_id": task.task_id, "attempt": task.attempt}

    worker = make_worker(queue, store, flaky)

    for _ in range(10):
        assert worker.run_once() == "retry"
    assert set(attempts_seen) == {1}, "the outage consumed attempts"
    assert worker.run_once() == "completed"
    assert store.has_result("id-414")
    assert not store.has_terminal_failure("id-414")


def test_the_refund_is_bounded_and_parks_with_a_named_reason() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(make_task())

    def permanent_outage(_task: TaskEnvelope):
        raise ProviderUnavailable("Ollama call failed: connection refused")

    worker = make_worker(queue, store, permanent_outage, max_attempts=2, refunds=2)
    ceiling = 2 + 2

    outcomes = [worker.run_once() for _ in range(ceiling)]
    assert set(outcomes) == {"retry"}
    assert len(queue.pending) == 1

    assert worker.run_once() == "dead-letter"
    assert store.has_terminal_failure("id-414")
    assert store.failures[-1]["terminal_reason"] == "provider_unavailable"
    assert "refund budget exhausted" in store.failures[-1]["error"]
    assert len(queue.dead_letters) == 1


@pytest.mark.parametrize(
    "exc",
    [ValueError("1 validation error for DNAStatementBatch"), RuntimeError("boom")],
    ids=["validation", "runtime"],
)
def test_a_content_failure_still_spends_attempts(exc: Exception) -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(make_task())

    def broken(_task: TaskEnvelope):
        raise exc

    worker = make_worker(queue, store, broken, max_attempts=3)

    assert worker.run_once() == "retry"
    assert queue.pending[0].task.attempt == 2, "a content failure must advance the attempt"
    assert store.failures[-1]["terminal"] is False

    assert worker.run_once() == "retry"
    assert worker.run_once() == "dead-letter"
    assert store.failures[-1]["terminal"] is True
    assert not store.has_terminal_failure("id-414") is False


def test_a_truncation_is_still_immediately_terminal() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(make_task())

    def truncating(_task: TaskEnvelope):
        raise LLMTruncationError("structured generation truncated")

    worker = make_worker(queue, store, truncating, max_attempts=3)

    assert worker.run_once() == "dead-letter"
    assert store.failures[-1]["terminal"] is True
