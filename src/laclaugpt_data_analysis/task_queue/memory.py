"""In-process task queue and result store.

These adapters need no server and no network, which makes them the default
surface for tests and for single-process runs. They implement the same protocols
as the durable adapters in ``sqlite_store.py``, ``mongo_store.py`` and
``redis_queue.py``, so the worker loop under test is the production loop.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from .models import (
    ClaimedTask,
    TaskEnvelope,
    bounded_failure_diagnostics,
    result_matches_fingerprint,
    result_supersedes_fingerprint,
)


class InMemoryTaskQueue:
    """List-backed queue: published tasks wait in order, claimed tasks stay reclaimable.

    `reclaim` ignores the idle threshold because in-process work has no transport
    clock; it simply hands back an unacknowledged task.
    """

    def __init__(self) -> None:
        self.pending: list[ClaimedTask] = []
        self.claimed: dict[str, ClaimedTask] = {}
        self.dead_letters: list[dict[str, Any]] = []
        self.heartbeats: list[dict[str, str]] = []
        self._counter = 0

    def publish(self, task: TaskEnvelope) -> str:
        task.validate()
        self._counter += 1
        message_id = str(self._counter)
        self.pending.append(ClaimedTask(message_id=message_id, task=task))
        return message_id

    def claim(self) -> ClaimedTask | None:
        if not self.pending:
            return None
        claimed = self.pending.pop(0)
        self.claimed[claimed.message_id] = claimed
        return claimed

    def reclaim(self, *, min_idle_ms: int) -> ClaimedTask | None:
        del min_idle_ms
        if not self.claimed:
            return None
        return next(iter(self.claimed.values()))

    def ack(self, message_id: str) -> None:
        self.claimed.pop(message_id, None)

    def dead_letter(self, task: TaskEnvelope, error: str) -> None:
        self.dead_letters.append({"task": task.to_dict(), "error": error})

    def heartbeat(self, **fields: str) -> None:
        self.heartbeats.append(dict(fields))


class InMemoryTaskStore:
    """Dict-backed result history, including terminal-failure and rearm semantics."""

    def __init__(self) -> None:
        self.results: dict[str, dict[str, Any]] = {}
        self.failures: list[dict[str, Any]] = []
        self.terminal_failures: set[str] = set()

    def has_result(self, idempotency_key: str, fingerprint: str = "") -> bool:
        stored = self.results.get(idempotency_key)
        if stored is None:
            return False
        return result_matches_fingerprint(stored, fingerprint)

    def has_terminal_failure(self, idempotency_key: str) -> bool:
        return idempotency_key in self.terminal_failures

    def has_recent_capacity_failure(
        self, idempotency_key: str, *, within_seconds: float
    ) -> bool:
        if within_seconds <= 0:
            return False
        cutoff = time.time() - within_seconds
        return any(
            row["task"]["idempotency_key"] == idempotency_key
            and row.get("provider_condition") == "no_gpu_capacity"
            and float(row.get("created_at") or 0) >= cutoff
            for row in self.failures
        )

    def rearm_terminal_failure(self, idempotency_key: str) -> int:
        if idempotency_key not in self.terminal_failures:
            return 0
        rearmed = 0
        now = time.time()
        for row in self.failures:
            if (
                row["task"]["idempotency_key"] == idempotency_key
                and row.get("terminal") is True
                and "rearmed_at" not in row
            ):
                row["rearmed_at"] = now
                rearmed += 1
        self.terminal_failures.discard(idempotency_key)
        return rearmed or 1

    def rearm_terminal_failure_if_budget_increased(
        self, idempotency_key: str, current_ceiling: int
    ) -> int:
        if current_ceiling < 1:
            return 0
        rearmed = 0
        now = time.time()
        for row in self.failures:
            if (
                row["task"]["idempotency_key"] == idempotency_key
                and row.get("terminal") is True
                and "rearmed_at" not in row
                and row.get("terminal_reason") == "unanalysable_within_budget"
                and isinstance(row.get("output_budget_tokens"), int)
                and row["output_budget_tokens"] < current_ceiling
            ):
                row["rearmed_at"] = now
                rearmed += 1
        if rearmed and not any(
            row["task"]["idempotency_key"] == idempotency_key
            and row.get("terminal") is True
            and "rearmed_at" not in row
            for row in self.failures
        ):
            self.terminal_failures.discard(idempotency_key)
        return rearmed

    def failure_summary(self) -> dict[str, int]:
        return {
            "events": len(self.failures),
            "distinct": len({row["task"]["idempotency_key"] for row in self.failures}),
            "terminal": len(self.terminal_failures),
        }

    def write_result(
        self,
        task: TaskEnvelope,
        result: Mapping[str, Any],
        provenance: Mapping[str, Any],
        *,
        fingerprint: str = "",
    ) -> bool:
        stored = self.results.get(task.idempotency_key)
        if stored is not None and not result_supersedes_fingerprint(stored, fingerprint):
            return False
        self.results[task.idempotency_key] = {
            "task": task.to_dict(),
            "result": dict(result),
            "provenance": dict(provenance),
            "generation_fingerprint": fingerprint,
        }
        return True

    def write_failure(
        self,
        task: TaskEnvelope,
        error: str,
        provenance: Mapping[str, Any],
        diagnostics: Mapping[str, Any] | None = None,
        *,
        terminal: bool = False,
    ) -> None:
        self.failures.append(
            {
                "task": task.to_dict(),
                "error": error,
                "provenance": dict(provenance),
                "terminal": terminal,
                "created_at": time.time(),
                **bounded_failure_diagnostics(diagnostics),
            }
        )
        if terminal:
            self.terminal_failures.add(task.idempotency_key)
