from __future__ import annotations

from types import SimpleNamespace

from laclaugpt_data_analysis.distributed_worker import seed_ready_tasks


class FakeBinding:
    manifest = SimpleNamespace(run_id="ai26-run")

    @staticmethod
    def task_from_handoff(handoff):
        return SimpleNamespace(idempotency_key=handoff["handoff_key"])


class FakeHandoff:
    def __init__(self, count: int):
        self.rows = [
            {
                "status": "ready",
                "run_id": "ai26-run",
                "handoff_key": f"handoff-{index}",
                "source_url": f"https://example.invalid/{index}",
            }
            for index in range(count)
        ]

    def ready_handoffs(self, run_id: str, *, limit: int, offset: int = 0):
        assert run_id == "ai26-run"
        return self.rows[offset : offset + limit]


class FakeQueue:
    def __init__(self):
        self.published = []

    def publish(self, task):
        self.published.append(task)


class FakeDurableStore:
    def __init__(self):
        self.completed: set[str] = set()

    def has_result(self, idempotency_key: str) -> bool:
        return idempotency_key in self.completed


def test_repeated_seed_cycles_advance_past_completed_head_page():
    binding = FakeBinding()
    handoff = FakeHandoff(10)
    durable = FakeDurableStore()
    seen: list[str] = []

    for _ in range(4):
        queue = FakeQueue()
        seeded = seed_ready_tasks(
            binding,
            handoff,
            queue,
            durable,
            limit=3,
        )
        assert seeded == len(queue.published)
        assert seeded <= 3
        keys = [task.idempotency_key for task in queue.published]
        assert not durable.completed.intersection(keys)
        durable.completed.update(keys)
        seen.extend(keys)

    assert seen == [f"handoff-{index}" for index in range(10)]

    queue = FakeQueue()
    assert seed_ready_tasks(binding, handoff, queue, durable, limit=3) == 0
    assert queue.published == []
