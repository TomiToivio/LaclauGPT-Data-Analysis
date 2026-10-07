"""Regression for issue #321: old truncation dead letters recover after ceiling increases."""
from __future__ import annotations

import sqlite3

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.distributed_worker import seed_ready_tasks
from laclaugpt_data_analysis.task_queue import (
    InMemoryTaskQueue,
    InMemoryTaskStore,
    SqliteTaskStore,
    TaskEnvelope,
)


def task(key: str = "old-8192") -> TaskEnvelope:
    return TaskEnvelope(
        task_id=f"analysis:{key}",
        idempotency_key=key,
        project_id="ai26",
        run_id="test-run",
        task_type="analyze-record",
        record_ref=f"https://example.invalid/{key}",
        schema_version=SCHEMA_VERSION,
        config_revision="test-config",
        codebook_revision="test-codebook",
    )


class Binding:
    manifest = type("Manifest", (), {"run_id": "test-run"})()

    @staticmethod
    def task_from_handoff(handoff):
        return task(handoff["handoff_key"])


class Handoff:
    def __init__(self, *keys: str):
        self.rows = [
            {
                "status": "ready",
                "run_id": "test-run",
                "handoff_key": key,
                "source_url": f"https://example.invalid/{key}",
            }
            for key in keys
        ]

    def ready_handoffs(self, _run_id, *, limit, offset=0):
        return self.rows[offset:offset + limit]


def truncation_failure(store, key: str, budget: int) -> None:
    store.write_failure(
        task(key),
        "LLMTruncationError: exhausted output budget",
        {},
        diagnostics={
            "response_raw": '{"unfinished":',
            "finish_reason": "length",
            "terminal_reason": "unanalysable_within_budget",
            "output_budget_tokens": budget,
            "required_output_tokens_lower_bound": budget + 1,
            "generated_output_chars": 14,
        },
        terminal=True,
    )


def test_seed_rearms_old_truncation_when_runtime_ceiling_increases(monkeypatch) -> None:
    store = InMemoryTaskStore()
    truncation_failure(store, "old-8192", 8192)
    queue = InMemoryTaskQueue()
    monkeypatch.setenv("LACLAUGPT_MAX_STRUCTURED_NUM_PREDICT", "16384")

    assert seed_ready_tasks(Binding(), Handoff("old-8192"), queue, store, limit=1) == 1
    assert [claimed.task.idempotency_key for claimed in queue.pending] == ["old-8192"]
    assert store.failures[0]["rearmed_at"] > 0
    assert not store.has_terminal_failure("old-8192")


def test_seed_keeps_same_ceiling_truncation_pinned(monkeypatch) -> None:
    store = InMemoryTaskStore()
    truncation_failure(store, "current-16384", 16384)
    queue = InMemoryTaskQueue()
    monkeypatch.setenv("LACLAUGPT_MAX_STRUCTURED_NUM_PREDICT", "16384")

    assert seed_ready_tasks(Binding(), Handoff("current-16384"), queue, store, limit=1) == 0
    assert queue.pending == []
    assert store.has_terminal_failure("current-16384")


def test_seed_does_not_rearm_unrelated_terminal_failure(monkeypatch) -> None:
    store = InMemoryTaskStore()
    store.write_failure(
        task("schema-terminal"),
        "ValueError: immutable manifest mismatch",
        {},
        terminal=True,
    )
    queue = InMemoryTaskQueue()
    monkeypatch.setenv("LACLAUGPT_MAX_STRUCTURED_NUM_PREDICT", "32768")

    assert seed_ready_tasks(Binding(), Handoff("schema-terminal"), queue, store, limit=1) == 0
    assert queue.pending == []
    assert store.has_terminal_failure("schema-terminal")


def test_sqlite_persists_budget_diagnostics_and_rearms_only_lower_ceiling(tmp_path) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    truncation_failure(store, "sqlite-old", 8192)

    with sqlite3.connect(store.path) as connection:
        row = connection.execute(
            "SELECT terminal_reason, output_budget_tokens, "
            "required_output_tokens_lower_bound, generated_output_chars "
            "FROM task_failures WHERE idempotency_key = ?",
            ("sqlite-old",),
        ).fetchone()
    assert row == ("unanalysable_within_budget", 8192, 8193, 14)

    assert store.rearm_terminal_failure_if_budget_increased("sqlite-old", 8192) == 0
    assert store.has_terminal_failure("sqlite-old")
    assert store.rearm_terminal_failure_if_budget_increased("sqlite-old", 16384) == 1
    assert not store.has_terminal_failure("sqlite-old")
