from pathlib import Path

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.distributed_worker import AI26TaskWorker, _cycle_exit_code
from laclaugpt_data_analysis.task_queue import InMemoryTaskQueue, SqliteTaskStore, TaskEnvelope


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


def test_cycle_fails_when_only_retry_or_dead_letter_work_happened() -> None:
    assert _cycle_exit_code({"completed": 0, "duplicate": 0, "retry": 1, "dead-letter": 0}) == 1
    assert _cycle_exit_code({"completed": 0, "duplicate": 0, "retry": 0, "dead-letter": 1}) == 1
    assert _cycle_exit_code({"completed": 0, "duplicate": 2, "retry": 1, "dead-letter": 0}) == 1


def test_cycle_succeeds_for_idle_duplicate_or_any_completed_progress() -> None:
    assert _cycle_exit_code({"completed": 0, "duplicate": 0, "retry": 0, "dead-letter": 0}) == 0
    assert _cycle_exit_code({"completed": 0, "duplicate": 3, "retry": 0, "dead-letter": 0}) == 0
    assert _cycle_exit_code({"completed": 1, "duplicate": 0, "retry": 1, "dead-letter": 1}) == 0


def test_worker_exposes_failure_class_without_failure_text(tmp_path: Path) -> None:
    queue = InMemoryTaskQueue()
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
    queue.publish(_task())

    def broken(_: TaskEnvelope):
        raise RuntimeError("sensitive source-derived failure detail")

    worker = AI26TaskWorker(queue, store, broken, "worker-1", {}, max_attempts=3)

    assert worker.run_once() == "retry"
    assert worker.last_failure_class == "RuntimeError"
    assert "sensitive" not in worker.last_failure_class


def test_failure_class_is_cleared_on_next_non_failure(tmp_path: Path) -> None:
    queue = InMemoryTaskQueue()
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
    task = _task()
    queue.publish(task)
    calls = 0

    def flaky(current: TaskEnvelope):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("temporary")
        return {"task_id": current.task_id}

    worker = AI26TaskWorker(queue, store, flaky, "worker-1", {}, max_attempts=3)

    assert worker.run_once() == "retry"
    assert worker.last_failure_class == "ValueError"
    assert worker.run_once() == "completed"
    assert worker.last_failure_class is None
