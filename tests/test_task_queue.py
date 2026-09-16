from pathlib import Path

from laclaugpt_data_analysis.task_queue import (
    InMemoryTaskQueue,
    SqliteTaskStore,
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


def test_direct_queue_and_sqlite_store_need_no_redis(tmp_path: Path) -> None:
    queue = InMemoryTaskQueue()
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
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


def test_duplicate_delivery_is_acknowledged_without_duplicate_result(tmp_path: Path) -> None:
    queue = InMemoryTaskQueue()
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
    calls = 0

    def handler(envelope: TaskEnvelope):
        nonlocal calls
        calls += 1
        return {"task_id": envelope.task_id}

    worker = TaskWorker(queue, store, handler, "worker-1", {"git_sha": "abc"})
    queue.publish(task())
    queue.publish(task(key="analysis:record-1:v1"))

    assert worker.run_once() == "completed"
    assert worker.run_once() == "duplicate"
    assert calls == 1


def test_failure_stays_pending_and_can_be_reclaimed(tmp_path: Path) -> None:
    queue = InMemoryTaskQueue()
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
    calls = 0

    def flaky(envelope: TaskEnvelope):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary")
        return {"task_id": envelope.task_id}

    queue.publish(task())
    worker = TaskWorker(queue, store, flaky, "worker-1", {})

    assert worker.run_once() == "retry"
    assert len(queue.pending) == 1
    assert worker.run_once(reclaim_idle_ms=1) == "completed"
    assert len(queue.pending) == 0


def test_result_is_durable_before_ack(tmp_path: Path) -> None:
    events: list[str] = []
    queue = InMemoryTaskQueue()
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
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
    worker = TaskWorker(queue, store, lambda _: {"ok": True}, "worker-1", {})

    assert worker.run_once() == "completed"
    assert events == ["write", "ack"]


def test_max_attempt_failure_goes_to_dead_letter(tmp_path: Path) -> None:
    queue = InMemoryTaskQueue()
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
    queue.publish(task(attempt=3))
    worker = TaskWorker(
        queue,
        store,
        lambda _: (_ for _ in ()).throw(ValueError("bad input")),
        "worker-1",
        {},
        max_attempts=3,
    )

    assert worker.run_once() == "dead-letter"
    assert len(queue.dead) == 1
    assert len(queue.pending) == 0


def test_validator_rejects_mismatched_run_before_analysis(tmp_path: Path) -> None:
    queue = InMemoryTaskQueue()
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
    queue.publish(task())

    def validate(envelope: TaskEnvelope) -> None:
        if envelope.run_id != "expected-run":
            raise ValueError("run mismatch")

    worker = TaskWorker(queue, store, lambda _: {"ok": True}, "worker-1", {}, validator=validate)

    try:
        worker.run_once()
    except ValueError as exc:
        assert "run mismatch" in str(exc)
    else:
        raise AssertionError("validator should reject incompatible task")


def test_task_envelope_contains_references_not_research_payload() -> None:
    fields = task().to_fields()
    assert "record_ref" in fields
    assert "payload" not in fields
    assert "text" not in fields
    assert "content" not in fields
