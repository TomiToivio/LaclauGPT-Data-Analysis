"""Distributed task queue: contracts, adapters and the worker loop.

The package is split by responsibility, so a reader can open the one module that
answers their question:

* ``models.py`` -- what a task is, and what a queue or store must do;
* ``memory.py`` -- in-process adapters, for tests and single-process runs;
* ``sqlite_store.py`` -- durable local result history in one file;
* ``mongo_store.py`` -- durable distributed result history;
* ``redis_queue.py`` -- Redis Streams transport between workers;
* ``worker.py`` -- the claim/analyse/acknowledge loop.

This module re-exports the historical ``laclaugpt_data_analysis.task_queue``
surface, so existing imports keep working unchanged while new code can import
from the specific module that owns the behaviour.
"""

from __future__ import annotations

from .memory import InMemoryTaskQueue, InMemoryTaskStore
from .models import (
    FAILURE_RESPONSE_RAW_MAX_CHARS,
    ClaimedTask,
    DurableTaskStore,
    TaskEnvelope,
    TaskQueue,
    bounded_failure_diagnostics,
    result_matches_fingerprint,
    result_supersedes_fingerprint,
)
from .mongo_store import MongoTaskStore
from .redis_queue import RedisStreamQueue
from .sqlite_store import SqliteTaskStore
from .worker import (
    TaskWorker,
    durable_store_from_settings,
    redis_queue_from_settings,
)

__all__ = [
    "FAILURE_RESPONSE_RAW_MAX_CHARS",
    "ClaimedTask",
    "DurableTaskStore",
    "InMemoryTaskQueue",
    "InMemoryTaskStore",
    "MongoTaskStore",
    "RedisStreamQueue",
    "SqliteTaskStore",
    "TaskEnvelope",
    "TaskQueue",
    "TaskWorker",
    "bounded_failure_diagnostics",
    "durable_store_from_settings",
    "redis_queue_from_settings",
    "result_matches_fingerprint",
    "result_supersedes_fingerprint",
]
