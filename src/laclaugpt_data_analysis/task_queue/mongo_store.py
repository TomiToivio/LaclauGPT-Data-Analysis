"""MongoDB-backed durable task result and failure history.

This is the distributed option: every worker in a run writes into the same
project/run-scoped collections, and a unique index on
``(project_id, run_id, idempotency_key)`` is what makes a second write of the
same task a duplicate rather than a second row.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from ..storage import mongo_client
from ..timequery import now_utc
from .models import (
    TaskEnvelope,
    bounded_failure_diagnostics,
    result_matches_fingerprint,
    result_supersedes_fingerprint,
)


class MongoTaskStore:
    """Durable distributed result/failure history with canonical source identity."""

    def __init__(
        self,
        mongo_url: str,
        *,
        database: str,
        result_collection: str,
        failure_collection: str,
        project_id: str,
        run_id: str,
    ) -> None:
        client = mongo_client(mongo_url)
        db = client[database]
        self.results = db[result_collection]
        self.failures = db[failure_collection]
        self.project_id = project_id
        self.run_id = run_id
        self.results.create_index(
            [("project_id", 1), ("run_id", 1), ("idempotency_key", 1)],
            unique=True,
            name="analysis_result_idempotency",
        )
        self.results.create_index(
            [("project_id", 1), ("run_id", 1), ("source_url", 1)],
            name="analysis_result_source_url",
        )
        self.failures.create_index(
            [("project_id", 1), ("run_id", 1), ("idempotency_key", 1)],
            name="analysis_failure_idempotency",
        )
        self.failures.create_index(
            [("project_id", 1), ("run_id", 1), ("source_url", 1)],
            name="analysis_failure_source_url",
        )

    def has_result(self, idempotency_key: str, fingerprint: str = "") -> bool:
        document = self.results.find_one(
            {
                "project_id": self.project_id,
                "run_id": self.run_id,
                "idempotency_key": idempotency_key,
            },
            {"_id": 0, "generation_fingerprint": 1},
        )
        if document is None:
            return False
        return result_matches_fingerprint(document, fingerprint)

    def has_terminal_failure(self, idempotency_key: str) -> bool:
        return (
            self.failures.find_one(
                {
                    "project_id": self.project_id,
                    "run_id": self.run_id,
                    "idempotency_key": idempotency_key,
                    "terminal": True,
                    "rearmed_at": {"$exists": False},
                },
                {"_id": 1},
            )
            is not None
        )

    def rearm_terminal_failure(self, idempotency_key: str) -> int:
        result = self.failures.update_many(
            {
                "project_id": self.project_id,
                "run_id": self.run_id,
                "idempotency_key": idempotency_key,
                "terminal": True,
                "rearmed_at": {"$exists": False},
            },
            {"$set": {"rearmed_at": time.time()}},
        )
        return int(result.modified_count)

    def rearm_terminal_failure_if_budget_increased(
        self, idempotency_key: str, current_ceiling: int
    ) -> int:
        if current_ceiling < 1:
            return 0
        result = self.failures.update_many(
            {
                "project_id": self.project_id,
                "run_id": self.run_id,
                "idempotency_key": idempotency_key,
                "terminal": True,
                "rearmed_at": {"$exists": False},
                "terminal_reason": "unanalysable_within_budget",
                "output_budget_tokens": {"$lt": current_ceiling},
            },
            {"$set": {"rearmed_at": time.time()}},
        )
        return int(result.modified_count)

    def failure_summary(self) -> dict[str, int]:
        base = {"project_id": self.project_id, "run_id": self.run_id}
        events = int(self.failures.count_documents(base))
        distinct = len(self.failures.distinct("idempotency_key", base))
        terminal_query = {**base, "terminal": True, "rearmed_at": {"$exists": False}}
        terminal = len(self.failures.distinct("idempotency_key", terminal_query))
        return {"events": events, "distinct": distinct, "terminal": terminal}

    def write_result(
        self,
        task: TaskEnvelope,
        result: Mapping[str, Any],
        provenance: Mapping[str, Any],
        *,
        fingerprint: str = "",
    ) -> bool:
        try:
            from pymongo.errors import DuplicateKeyError
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pymongo is required for MongoTaskStore") from exc
        source_url = str(task.record_ref or result.get("source_url") or "").strip()
        if not source_url:
            raise ValueError("analysis result cannot be persisted without canonical source_url")
        document = {
            "project_id": self.project_id,
            "run_id": self.run_id,
            "idempotency_key": task.idempotency_key,
            "source_url": source_url,
            "result": dict(result),
            "provenance": dict(provenance),
            "generation_fingerprint": fingerprint,
            # #504: a BSON datetime, not an epoch float - a float field silently matches nothing
            # against a datetime range query, which makes a stalled pipeline look like a quiet hour.
            "created_at": now_utc(),
        }
        try:
            self.results.insert_one(document)
            return True
        except DuplicateKeyError:
            query = {
                "project_id": self.project_id,
                "run_id": self.run_id,
                "idempotency_key": task.idempotency_key,
            }
            stored = self.results.find_one(query, {"_id": 0, "generation_fingerprint": 1})
            if not result_supersedes_fingerprint(stored, fingerprint):
                return False
            self.results.replace_one(query, document)
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
        self.failures.insert_one(
            {
                "project_id": self.project_id,
                "run_id": self.run_id,
                "task_id": task.task_id,
                "idempotency_key": task.idempotency_key,
                "source_url": task.record_ref,
                "attempt": task.attempt,
                "error": error,
                "provenance": dict(provenance),
                "terminal": terminal,
                **bounded_failure_diagnostics(diagnostics),
                # #504: use BSON datetime so standard range queries can find failures.
                "created_at": now_utc(),
            }
        )
