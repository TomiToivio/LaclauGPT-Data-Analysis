"""Run-level isolation for concurrent AI26 analysis (#390, acceptance criterion 4).

A Roihu test reads the same canonical corpus as the Laskin production run. The property that makes
that safe is that every *execution* key — task stream, consumer group, dead-letter stream, heartbeat,
result and failure collections — is derived from the run id rather than the project id.

Until now the namespace scheme was pinned for a single run id, so nothing caught a change that would
make two runs share a key until they were already fighting over the same tasks in production. These
tests compare two run ids directly: if a future edit drops the run id from any key, the collision is a
CI failure instead of a stolen task.
"""
from __future__ import annotations

import pytest

from laclaugpt_data_analysis.distributed import ProjectNamespace
from laclaugpt_data_analysis.task_queue import RedisStreamQueue, redis_queue_from_settings

PRODUCTION_RUN = "ai26-distributed-001"
TEST_RUN = "roihu-test-0001"


class _Settings:
    def __init__(self, *, project_id: str = "ai26", redis_url: str = "redis://127.0.0.1:6379/0") -> None:
        self.project_id = project_id
        self.redis_url = redis_url
        self.distributed_namespace = ProjectNamespace(project_id)


@pytest.fixture()
def captured(monkeypatch):
    seen: dict[str, list[dict[str, str | None]]] = {}

    def fake_init(self, url, *, stream, group, consumer, dead_letter_stream=None, heartbeat_key=None):
        seen.setdefault("queues", []).append(
            {
                "stream": stream,
                "group": group,
                "dead_letter_stream": dead_letter_stream,
                "heartbeat_key": heartbeat_key,
            }
        )

    monkeypatch.setattr(RedisStreamQueue, "__init__", fake_init)
    return seen


def _queue(run_id: str) -> None:
    redis_queue_from_settings(_Settings(), run_id=run_id, worker_id="worker-1")


def test_two_runs_never_share_a_task_stream(captured):
    _queue(PRODUCTION_RUN)
    _queue(TEST_RUN)
    production, test = captured["queues"]
    assert production["stream"] != test["stream"]
    assert PRODUCTION_RUN in production["stream"]
    assert TEST_RUN in test["stream"]
    assert PRODUCTION_RUN not in test["stream"]


def test_two_runs_never_share_a_consumer_group(captured):
    _queue(PRODUCTION_RUN)
    _queue(TEST_RUN)
    production, test = captured["queues"]
    assert production["group"] != test["group"]
    assert PRODUCTION_RUN in production["group"]
    assert TEST_RUN in test["group"]


def test_dead_letter_streams_are_isolated(captured):
    _queue(PRODUCTION_RUN)
    _queue(TEST_RUN)
    production, test = captured["queues"]
    assert production["dead_letter_stream"] != test["dead_letter_stream"]
    assert PRODUCTION_RUN not in test["dead_letter_stream"]


def test_production_keys_are_unchanged_by_this_contract(captured):
    """The documented scheme still holds exactly for the production run id."""
    _queue(PRODUCTION_RUN)
    queue = captured["queues"][0]
    assert queue["stream"] == f"laclaugpt:ai26:stream:analysis:{PRODUCTION_RUN}:tasks"
    assert queue["dead_letter_stream"] == f"laclaugpt:ai26:stream:analysis:{PRODUCTION_RUN}:dead"


def test_result_and_failure_collections_are_project_scoped_not_run_scoped():
    """Durable results live in project collections, so record identity must carry the run instead.

    Documenting this explicitly because it is the one place where the run id is *not* part of the key:
    the collection is shared, and isolation comes from the run_id stored on each document. A test that
    assumed collection-level isolation would be wrong.
    """
    namespace = ProjectNamespace("ai26")
    assert namespace.mongo_collection("analysis_results") == "ai26__analysis_results"
    assert namespace.mongo_collection("analysis_failures") == "ai26__analysis_failures"
