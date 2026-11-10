"""A provider outage must not spend the document's retry budget (#414).

Ten AI26 documents were quarantined as `terminal=true` because Ollama answered HTTP 500 three times
inside one outage. The failure said something about the endpoint, not about the document: the same
handoff analyses perfectly once the provider is healthy, so the attempt counter must not move and the
task must never dead-letter on an infrastructure error alone.

The other half of the test is that this did not turn every failure into an infinite loop: a content
error still advances the attempt and still reaches the dead-letter queue, and a long outage stops
re-queueing the same document within one worker run instead of spinning on it for the whole cycle.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION  # noqa: E402
from laclaugpt_data_analysis.distributed_worker import (  # noqa: E402
    INFRASTRUCTURE_REFUND_LIMIT,
    AI26TaskWorker,
    is_infrastructure_failure,
)
from laclaugpt_data_analysis.llm.base import (  # noqa: E402
    LLMEmptyResponseError,
    LLMTruncationError,
    ProviderError,
)
from laclaugpt_data_analysis.task_queue import (  # noqa: E402
    InMemoryTaskQueue,
    InMemoryTaskStore,
    TaskEnvelope,
)


def _task(attempt: int = 1) -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task-1",
        idempotency_key="id-1",
        project_id="ai26",
        run_id="ai26-distributed-001",
        task_type="analyze-record",
        record_ref="https://x.com/AnthropicAI/status/2114705042817110293",
        attempt=attempt,
        schema_version=SCHEMA_VERSION,
        config_revision="cfg",
        codebook_revision="cb",
    )


def _worker(handler, *, max_attempts: int = 3):
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(_task())
    worker = AI26TaskWorker(
        queue=queue,
        durable_store=store,
        handler=handler,
        worker_id="worker-1",
        provenance={},
        max_attempts=max_attempts,
    )
    return worker, queue, store


def _raising(exc: BaseException):
    def handler(_task):
        raise exc

    return handler


def test_a_provider_500_is_infrastructure_and_truncation_is_not():
    assert is_infrastructure_failure(ProviderError("Ollama call failed: 500"))
    assert not is_infrastructure_failure(LLMTruncationError("length stop"))
    assert not is_infrastructure_failure(LLMEmptyResponseError("empty"))
    assert not is_infrastructure_failure(ValueError("bad input"))


def test_a_provider_outage_does_not_advance_the_attempt():
    worker, queue, store = _worker(_raising(ProviderError("Ollama call failed: 500 Internal Server Error")))

    assert worker.run_once() == "retry"
    assert store.failures[-1]["terminal"] is False
    assert store.failures[-1]["task"]["attempt"] == 1
    # the re-queued task is the same attempt: the document has not spent one
    assert queue.pending[-1].task.attempt == 1
    assert store.has_terminal_failure("id-1") is False


def test_the_same_document_is_not_re_queued_forever_inside_one_run():
    worker, queue, store = _worker(_raising(ProviderError("Ollama call failed: 503")))

    for _ in range(INFRASTRUCTURE_REFUND_LIMIT):
        assert worker.run_once() == "retry"
        assert queue.pending, "an infrastructure failure is re-queued while the limit lasts"

    # Beyond the limit the message is dropped for this run and left to the next seed cycle:
    # no publish, no attempt spent, no terminal record.
    assert worker.run_once() == "retry"
    assert queue.pending == [], "past the limit the message is dropped for this run, not re-queued"
    assert store.has_terminal_failure("id-1") is False


def test_a_content_failure_still_reaches_the_dead_letter_queue():
    worker, queue, store = _worker(_raising(RuntimeError("still broken")), max_attempts=3)

    assert worker.run_once() == "retry"
    assert store.failures[-1]["task"]["attempt"] == 1
    assert worker.run_once() == "retry"
    assert store.failures[-1]["task"]["attempt"] == 2
    assert worker.run_once() == "dead-letter"
    assert store.failures[-1]["terminal"] is True


def test_infrastructure_diagnostics_are_marked_as_such():
    worker, _, store = _worker(_raising(ProviderError("Ollama call failed: 500")))
    worker.run_once()
    assert store.failures[-1].get("infrastructure") is True
