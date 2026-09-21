from __future__ import annotations

from pydantic import BaseModel

from laclaugpt_data_analysis.distributed_worker import AI26TaskWorker
from laclaugpt_data_analysis.llm.base import (
    ChatRequest,
    LLMCallProvenance,
    LLMResponse,
)
from laclaugpt_data_analysis.llm.structured_output import chat_structured
from laclaugpt_data_analysis.task_queue import (
    FAILURE_RESPONSE_RAW_MAX_CHARS,
    InMemoryTaskQueue,
    InMemoryTaskStore,
    TaskEnvelope,
)


class _Payload(BaseModel):
    value: str


def _provenance() -> LLMCallProvenance:
    return LLMCallProvenance(
        requested_mode="local",
        requested_model="test-model",
        resolved_model="test-model",
        actual_mode="local",
        actual_model="test-model",
    )


def test_failed_structured_response_is_bounded_and_persisted_for_diagnosis() -> None:
    raw = '{"value":"' + ("x" * 20_000)

    class MalformedProvider:
        def chat(self, request: ChatRequest) -> LLMResponse:
            del request
            return LLMResponse(
                content=raw,
                provenance=_provenance(),
                finish_reason="stop",
                truncated=False,
            )

    provider = MalformedProvider()
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    task = TaskEnvelope(
        task_id="task-283",
        idempotency_key="id-283",
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref="https://example.invalid/source/283",
        schema_version="test-schema",
        config_revision="cfg",
        codebook_revision="cb",
    )
    queue.publish(task)

    def handler(_: TaskEnvelope) -> dict[str, str]:
        parsed, _response = chat_structured(
            provider,
            _Payload,
            model="test-model",
            system_prompt="system",
            user_prompt="user",
        )
        return parsed.model_dump()

    worker = AI26TaskWorker(
        queue=queue,
        durable_store=store,
        handler=handler,
        worker_id="worker-283",
        provenance={"model": "test-model"},
        max_attempts=1,
    )

    assert worker.run_once() == "dead-letter"
    assert worker.last_failure_class == "JSONDecodeError"
    assert len(store.failures) == 1

    failure = store.failures[0]
    assert failure["task"]["task_id"] == "task-283"
    assert failure["finish_reason"] == "stop"
    assert failure["response_raw"] == raw[:FAILURE_RESPONSE_RAW_MAX_CHARS]
    assert failure["response_raw_chars"] == len(raw)
    assert failure["response_raw_truncated"] is True
    assert failure["diagnostic_only"] is True
    assert "result" not in failure
