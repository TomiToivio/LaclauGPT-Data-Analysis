from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.distributed_worker import (
    AI26TaskWorker,
    _cycle_exit_code,
    _run_bounded_cycle,
)
from laclaugpt_data_analysis.task_queue import InMemoryTaskQueue, InMemoryTaskStore, TaskEnvelope


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


def test_worker_exposes_failure_class_without_failure_text() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    queue.publish(_task())

    def broken(_: TaskEnvelope):
        raise RuntimeError("sensitive source-derived failure detail")

    worker = AI26TaskWorker(
        queue=queue,
        durable_store=store,
        handler=broken,
        worker_id="worker-1",
        provenance={},
        max_attempts=3,
    )

    assert worker.run_once() == "retry"
    assert worker.last_failure_class == "RuntimeError"
    assert "sensitive" not in worker.last_failure_class


def test_failure_class_is_cleared_on_next_non_failure() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    task = _task()
    queue.publish(task)
    calls = 0

    def flaky(current: TaskEnvelope):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("temporary")
        return {"task_id": current.task_id}

    worker = AI26TaskWorker(
        queue=queue,
        durable_store=store,
        handler=flaky,
        worker_id="worker-1",
        provenance={},
        max_attempts=3,
    )

    assert worker.run_once() == "retry"
    assert worker.last_failure_class == "ValueError"
    assert worker.run_once() == "completed"
    assert worker.last_failure_class is None


class _OutcomeWorker:
    def __init__(self, outcomes: list[str]):
        self.outcomes = iter(outcomes)
        self.last_failure_class = None
        self.last_quarantined = 0

    def run_once(self, *, reclaim_idle_ms=None) -> str:
        del reclaim_idle_ms
        return next(self.outcomes)


def test_duplicate_backlog_does_not_consume_work_budget() -> None:
    worker = _OutcomeWorker(["duplicate"] * 120 + ["completed"] * 5)
    counts, failures = _run_bounded_cycle(
        worker,
        max_tasks=5,
        reclaim_idle_ms=900_000,
        seeded=5,
    )

    assert counts["duplicate"] == 120
    assert counts["completed"] == 5
    assert counts["claims"] == 125
    assert failures == {}
    assert _cycle_exit_code(counts) == 0


def test_seeded_but_no_progress_is_visible_as_failure() -> None:
    worker = _OutcomeWorker(["duplicate"] * 10)
    counts, _ = _run_bounded_cycle(
        worker,
        max_tasks=5,
        reclaim_idle_ms=900_000,
        max_claims=10,
        seeded=5,
    )

    assert counts["completed"] == 0
    assert counts["duplicate"] == 10
    assert counts["claims"] == 10
    assert _cycle_exit_code(counts) == 1
