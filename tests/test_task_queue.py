from laclaugpt_data_analysis.task_queue import (
    InMemoryTaskQueue,
    InMemoryTaskStore,
    TaskEnvelope,
    TaskWorker,
)


def task(*, attempt: int = 1, key: str = "analysis:record-1:v1") -> TaskEnvelope:
    return TaskEnvelope(
        task_id=f"task-{attempt}",
        idempotency_key=key,
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref="mongodb://laclaugpt/ai26__raw/source-1",
        schema_version="1",
        config_revision="cfg-abc",
        codebook_revision="cb-def",
        attempt=attempt,
    )


def test_direct_queue_and_in_memory_store_need_no_redis() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(task())
    worker = TaskWorker(
        queue=queue,
        durable_store=store,
        handler=lambda envelope: {"source": envelope.record_ref, "ok": True},
        worker_id="local-1",
        provenance={"mode": "direct"},
    )

    assert worker.run_once() == "completed"
    assert store.has_result("analysis:record-1:v1")


def test_duplicate_delivery_is_acknowledged_without_duplicate_result() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    calls = 0

    def handler(envelope: TaskEnvelope):
        nonlocal calls
        calls += 1
        return {"task_id": envelope.task_id}

    worker = TaskWorker(
        queue=queue,
        durable_store=store,
        handler=handler,
        worker_id="worker-1",
        provenance={"git_sha": "abc"},
    )
    queue.publish(task())
    queue.publish(task(key="analysis:record-1:v1"))

    assert worker.run_once() == "completed"
    assert worker.run_once() == "duplicate"
    assert calls == 1


def test_failure_requeues_with_incremented_attempt() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    calls = 0

    def flaky(envelope: TaskEnvelope):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary")
        return {"task_id": envelope.task_id}

    queue.publish(task())
    worker = TaskWorker(
        queue=queue,
        durable_store=store,
        handler=flaky,
        worker_id="worker-1",
        provenance={},
    )

    assert worker.run_once() == "retry"
    assert len(queue.pending) == 1
    assert queue.pending[0].task.attempt == 2
    assert worker.run_once() == "completed"
    assert len(queue.pending) == 0


def test_result_is_written_before_ack() -> None:
    events: list[str] = []
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    original_ack = queue.ack
    original_write = store.write_result

    def write(*args, **kwargs):
        events.append("write")
        return original_write(*args, **kwargs)

    def ack(message_id: str):
        events.append("ack")
        original_ack(message_id)

    store.write_result = write  # type: ignore[method-assign]
    queue.ack = ack  # type: ignore[method-assign]
    queue.publish(task())
    worker = TaskWorker(
        queue=queue,
        durable_store=store,
        handler=lambda _: {"ok": True},
        worker_id="worker-1",
        provenance={},
    )

    assert worker.run_once() == "completed"
    assert events == ["write", "ack"]


def test_max_attempt_failure_goes_to_dead_letter() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(task(attempt=3))
    worker = TaskWorker(
        queue=queue,
        durable_store=store,
        handler=lambda _: (_ for _ in ()).throw(ValueError("bad input")),
        worker_id="worker-1",
        provenance={},
        max_attempts=3,
    )

    assert worker.run_once() == "dead-letter"
    assert len(queue.dead_letters) == 1
    assert queue.dead_letters[0]["task"]["attempt"] == 3
    assert len(queue.pending) == 0


def test_validator_rejects_mismatched_run_before_analysis() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(task())

    def validate(envelope: TaskEnvelope) -> None:
        if envelope.run_id != "expected-run":
            raise ValueError("run mismatch")

    worker = TaskWorker(
        queue=queue,
        durable_store=store,
        handler=lambda _: {"ok": True},
        worker_id="worker-1",
        provenance={},
        validator=validate,
    )

    try:
        worker.run_once()
    except ValueError as exc:
        assert "run mismatch" in str(exc)
    else:
        raise AssertionError("validator should reject incompatible task")


def test_task_envelope_contains_references_not_research_payload() -> None:
    fields = task().to_dict()
    assert "record_ref" in fields
    assert "payload" not in fields
    assert "text" not in fields
    assert "content" not in fields
