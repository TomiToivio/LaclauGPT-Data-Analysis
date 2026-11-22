"""The claim/analyse/acknowledge worker loop.

``TaskWorker`` is transport- and store-agnostic: it depends only on the two
protocols in ``models.py``. The factory functions at the bottom are the one place
that knows how the configured settings map onto concrete adapters.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Callable, Mapping

from ..config import Settings
from .models import DurableTaskStore, TaskEnvelope, TaskQueue
from .mongo_store import MongoTaskStore
from .redis_queue import RedisStreamQueue

logger = logging.getLogger(__name__)


class TaskWorker:
    """Claim one task, analyse it, and settle the claim.

    ``run_once`` returns a short outcome string rather than raising for ordinary
    conditions: ``idle`` (nothing to do), ``duplicate`` (a current result already
    exists), ``completed``, ``retry`` (republished with ``attempt + 1``) or
    ``dead-letter`` (the attempt ceiling was reached).
    """

    def __init__(
        self,
        *,
        queue: TaskQueue,
        durable_store: DurableTaskStore,
        handler: Callable[[TaskEnvelope], Mapping[str, Any]],
        worker_id: str,
        provenance: Mapping[str, Any],
        validator: Callable[[TaskEnvelope], None] | None = None,
        max_attempts: int = 3,
        generation_fingerprint: str = "",
    ) -> None:
        self.queue = queue
        self.durable_store = durable_store
        self.handler = handler
        self.worker_id = worker_id
        self.provenance = dict(provenance)
        self.validator = validator
        self.max_attempts = max_attempts
        #: Resume identity of the *effective* generation settings (issue #372). Empty
        #: keeps the historical presence-only duplicate check.
        self.generation_fingerprint = generation_fingerprint
        self.last_resume_invalidated = 0

    def has_current_result(self, task: TaskEnvelope) -> bool:
        """Whether a result already exists for this source *and these settings*.

        A stored result written under different effective generation settings is not a
        duplicate: it is a stale answer to a question the run is no longer asking. The
        worker re-analyses it and says so in the log.
        """
        store = self.durable_store
        key = task.idempotency_key
        fingerprint = self.generation_fingerprint
        if store.has_result(key, fingerprint):
            return True
        if fingerprint and store.has_result(key):
            logger.warning(
                "resume_invalidated idempotency_key=%s reason=generation_settings_changed "
                "fingerprint=%s; re-analysing instead of reusing the stored result",
                key,
                fingerprint,
            )
            self.last_resume_invalidated += 1
        return False

    def run_once(self, *, reclaim_idle_ms: int | None = None) -> str:
        self.last_failure_class = None
        claimed = None
        if reclaim_idle_ms is not None:
            claimed = self.queue.reclaim(min_idle_ms=reclaim_idle_ms)
        if claimed is None:
            claimed = self.queue.claim()
        if claimed is None:
            return "idle"

        task = claimed.task
        if self.validator is not None:
            self.validator(task)

        if self.has_current_result(task):
            self.queue.ack(claimed.message_id)
            return "duplicate"

        try:
            result = self.handler(task)
            inserted = self.durable_store.write_result(
                task,
                result,
                self.provenance,
                fingerprint=self.generation_fingerprint,
            )
            self.queue.ack(claimed.message_id)
            return "completed" if inserted else "duplicate"
        except Exception as exc:
            self.last_failure_class = type(exc).__name__
            error = f"{self.last_failure_class}: {exc}"
            self.durable_store.write_failure(task, error, self.provenance)
            if task.attempt >= self.max_attempts:
                self.queue.dead_letter(task, error)
                self.queue.ack(claimed.message_id)
                return "dead-letter"
            retry_task = replace(task, attempt=task.attempt + 1)
            retry_task.validate()
            self.queue.publish(retry_task)
            self.queue.ack(claimed.message_id)
            return "retry"

    def heartbeat(self, **fields: str) -> None:
        self.queue.heartbeat(worker_id=self.worker_id, **fields)


def redis_queue_from_settings(
    settings: Settings,
    *,
    run_id: str,
    worker_id: str,
) -> RedisStreamQueue:
    """Build a run-scoped Redis Streams queue from the active settings."""
    if not settings.redis_url:
        raise ValueError("LACLAUGPT_REDIS_URL is required for Redis task mode")
    namespace = settings.distributed_namespace
    return RedisStreamQueue(
        settings.redis_url,
        stream=namespace.stream_key(f"analysis:{run_id}:tasks"),
        group=namespace.redis_key("group", "analysis", run_id),
        consumer=worker_id,
        dead_letter_stream=namespace.stream_key(f"analysis:{run_id}:dead"),
        heartbeat_key=namespace.worker_key("analysis", worker_id),
    )


def durable_store_from_settings(settings: Settings, *, run_id: str) -> MongoTaskStore:
    """Build the run-scoped Mongo result store from the active settings."""
    namespace = settings.distributed_namespace
    return MongoTaskStore(
        settings.mongo_url,
        database=settings.mongo_database,
        result_collection=namespace.mongo_collection("analysis_results"),
        failure_collection=namespace.mongo_collection("analysis_failures"),
        project_id=settings.project_id,
        run_id=run_id,
    )
