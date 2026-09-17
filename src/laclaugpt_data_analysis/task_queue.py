"""Optional reference-only task queue for distributed analysis workers.

Redis is coordination only. Durable analysis results and failure history live in a
``DurableTaskStore`` implementation (SQLite locally, MongoDB in distributed mode).
Direct mode does not import or require Redis.
"""
from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class TaskEnvelope:
    task_id: str
    idempotency_key: str
    project_id: str
    run_id: str
    task_type: str
    record_ref: str
    schema_version: str
    config_revision: str
    codebook_revision: str
    attempt: int = 1

    def validate(self) -> None:
        required = {
            "task_id": self.task_id,
            "idempotency_key": self.idempotency_key,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "task_type": self.task_type,
            "record_ref": self.record_ref,
            "schema_version": self.schema_version,
            "config_revision": self.config_revision,
            "codebook_revision": self.codebook_revision,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError("task envelope missing: " + ", ".join(sorted(missing)))
        if self.attempt < 1:
            raise ValueError("attempt must be >= 1")

    def to_fields(self) -> dict[str, str]:
        self.validate()
        values = asdict(self)
        return {key: str(value) for key, value in values.items()}

    @classmethod
    def from_fields(cls, fields: Mapping[str, Any]) -> TaskEnvelope:
        task = cls(
            task_id=str(fields["task_id"]),
            idempotency_key=str(fields["idempotency_key"]),
            project_id=str(fields["project_id"]),
            run_id=str(fields["run_id"]),
            task_type=str(fields["task_type"]),
            record_ref=str(fields["record_ref"]),
            schema_version=str(fields["schema_version"]),
            config_revision=str(fields["config_revision"]),
            codebook_revision=str(fields["codebook_revision"]),
            attempt=int(fields.get("attempt", 1)),
        )
        task.validate()
        return task


@dataclass(frozen=True, slots=True)
class ClaimedTask:
    message_id: str
    task: TaskEnvelope


class TaskQueue(Protocol):
    def publish(self, task: TaskEnvelope) -> str: ...
    def claim(self, *, block_ms: int = 1000) -> ClaimedTask | None: ...
    def reclaim(self, *, min_idle_ms: int) -> ClaimedTask | None: ...
    def ack(self, message_id: str) -> None: ...
    def dead_letter(self, task: TaskEnvelope, error: str) -> None: ...
    def heartbeat(self, metadata: Mapping[str, str], *, ttl_seconds: int = 60) -> None: ...


class DurableTaskStore(Protocol):
    def has_result(self, idempotency_key: str) -> bool: ...
    def write_result(
        self,
        task: TaskEnvelope,
        result: Mapping[str, Any],
        provenance: Mapping[str, Any],
    ) -> bool: ...
    def write_failure(
        self,
        task: TaskEnvelope,
        error: str,
        provenance: Mapping[str, Any],
    ) -> None: ...


class SqliteTaskStore:
    """Tiny durable store for local/direct mode and offline tests."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS task_results ("
                "idempotency_key TEXT PRIMARY KEY, source_url TEXT, result_json TEXT NOT NULL, "
                "provenance_json TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(task_results)")
            }
            if "source_url" not in columns:
                connection.execute("ALTER TABLE task_results ADD COLUMN source_url TEXT")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS task_failures ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, "
                "idempotency_key TEXT NOT NULL, source_url TEXT, attempt INTEGER NOT NULL, "
                "error TEXT NOT NULL, provenance_json TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            failure_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(task_failures)")
            }
            if "source_url" not in failure_columns:
                connection.execute("ALTER TABLE task_failures ADD COLUMN source_url TEXT")

    def has_result(self, idempotency_key: str) -> bool:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT 1 FROM task_results WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
        return row is not None

    def write_result(
        self,
        task: TaskEnvelope,
        result: Mapping[str, Any],
        provenance: Mapping[str, Any],
    ) -> bool:
        try:
            with sqlite3.connect(self.path) as connection:
                connection.execute(
                    "INSERT INTO task_results "
                    "(idempotency_key, source_url, result_json, provenance_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        task.idempotency_key,
                        task.record_ref,
                        json.dumps(dict(result), ensure_ascii=False, default=str),
                        json.dumps(dict(provenance), ensure_ascii=False, default=str),
                        time.time(),
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def write_failure(
        self,
        task: TaskEnvelope,
        error: str,
        provenance: Mapping[str, Any],
    ) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO task_failures "
                "(task_id, idempotency_key, source_url, attempt, error, provenance_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    task.task_id,
                    task.idempotency_key,
                    task.record_ref,
                    task.attempt,
                    error,
                    json.dumps(dict(provenance), ensure_ascii=False, default=str),
                    time.time(),
                ),
            )


class MongoTaskStore:
    """Durable distributed result/failure history with canonical source identity."""

    def __init__(
        self,
        url: str,
        *,
        database: str,
        results_collection: str,
        failures_collection: str,
        project_id: str,
        run_id: str,
    ):
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise RuntimeError("MongoDB task support requires: pip install '.[remote]'") from exc
        client = MongoClient(url)
        db = client[database]
        self.results = db[results_collection]
        self.failures = db[failures_collection]
        self.project_id = project_id
        self.run_id = run_id
        self.results.create_index(
            [("project_id", 1), ("run_id", 1), ("idempotency_key", 1)],
            unique=True,
            name="project_run_idempotency",
        )
        self.results.create_index(
            [("project_id", 1), ("run_id", 1), ("source_url", 1)],
            name="project_run_source_url",
        )
        self.failures.create_index(
            [("project_id", 1), ("run_id", 1), ("idempotency_key", 1)],
            name="project_run_failure",
        )
        self.failures.create_index(
            [("project_id", 1), ("run_id", 1), ("source_url", 1)],
            name="project_run_failure_source_url",
        )

    def has_result(self, idempotency_key: str) -> bool:
        return (
            self.results.find_one(
                {
                    "project_id": self.project_id,
                    "run_id": self.run_id,
                    "idempotency_key": idempotency_key,
                },
                {"_id": 1},
            )
            is not None
        )

    def write_result(
        self,
        task: TaskEnvelope,
        result: Mapping[str, Any],
        provenance: Mapping[str, Any],
    ) -> bool:
        try:
            from pymongo.errors import DuplicateKeyError
        except ImportError as exc:
            raise RuntimeError("MongoDB task support requires: pip install '.[remote]'") from exc
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
            "created_at": time.time(),
        }
        try:
            self.results.insert_one(document)
            return True
        except DuplicateKeyError:
            return False

    def write_failure(
        self,
        task: TaskEnvelope,
        error: str,
        provenance: Mapping[str, Any],
    ) -> None:
        self.failures.insert_one(
            {
                "project_id": self.project_id,
                "run_id": self.run_id,
                "source_url": task.record_ref,
                "task_id": task.task_id,
                "idempotency_key": task.idempotency_key,
                "source_url": task.record_ref,
                "attempt": task.attempt,
                "error": error,
                "provenance": dict(provenance),
                "created_at": time.time(),
            }
        )


class RedisStreamQueue:
    """Redis Streams adapter using consumer groups and pending-entry reclaim."""

    _LEGACY_PENDING_BATCH = 100

    def __init__(
        self,
        url: str,
        *,
        stream: str,
        group: str,
        consumer: str,
        dead_letter_stream: str | None = None,
        heartbeat_key: str | None = None,
    ):
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Redis task support requires: pip install '.[remote]'") from exc
        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.stream = stream
        self.group = group
        self.consumer = consumer
        self.dead_letter_stream = dead_letter_stream or f"{stream}:dead"
        self.heartbeat_key = heartbeat_key or f"{stream}:worker:{consumer}"
        try:
            self.client.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    @staticmethod
    def _decode(value: Any) -> Any:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    @classmethod
    def _decode_fields(cls, fields: Mapping[Any, Any]) -> dict[str, Any]:
        return {str(cls._decode(key)): cls._decode(value) for key, value in fields.items()}

    @classmethod
    def _claimed_task(cls, message_id: Any, fields: Mapping[Any, Any]) -> ClaimedTask:
        return ClaimedTask(
            str(cls._decode(message_id)),
            TaskEnvelope.from_fields(cls._decode_fields(fields)),
        )

    @staticmethod
    def _next_stream_id(message_id: str) -> str:
        milliseconds, sequence = message_id.split("-", maxsplit=1)
        return f"{milliseconds}-{int(sequence) + 1}"

    @staticmethod
    def _is_xautoclaim_unknown_command(exc: Exception) -> bool:
        message = str(exc).lower()
        return "unknown command" in message and "xautoclaim" in message

    def publish(self, task: TaskEnvelope) -> str:
        return str(self.client.xadd(self.stream, task.to_fields()))

    def claim(self, *, block_ms: int = 1000) -> ClaimedTask | None:
        response = self.client.xreadgroup(
            self.group,
            self.consumer,
            {self.stream: ">"},
            count=1,
            block=block_ms,
        )
        if not response:
            return None
        _, messages = response[0]
        message_id, fields = messages[0]
        return self._claimed_task(message_id, fields)

    def reclaim(self, *, min_idle_ms: int) -> ClaimedTask | None:
        try:
            response = self.client.xautoclaim(
                self.stream,
                self.group,
                self.consumer,
                min_idle_ms,
                "0-0",
                count=1,
            )
        except Exception as exc:
            if not self._is_xautoclaim_unknown_command(exc):
                raise
            return self._reclaim_legacy(min_idle_ms=min_idle_ms)

        messages = response[1] if len(response) > 1 else []
        if not messages:
            return None
        message_id, fields = messages[0]
        return self._claimed_task(message_id, fields)

    def _reclaim_legacy(self, *, min_idle_ms: int) -> ClaimedTask | None:
        """Redis 5/6.0 fallback using XPENDING + XCLAIM.

        Redis 6.0 has neither XAUTOCLAIM nor XPENDING's IDLE filter, so inspect
        ordinary pending-entry metadata client-side and claim the first entry
        whose idle time meets the configured threshold.
        """
        start = "-"
        while True:
            pending = self.client.xpending_range(
                self.stream,
                self.group,
                min=start,
                max="+",
                count=self._LEGACY_PENDING_BATCH,
            )
            if not pending:
                return None

            for raw_entry in pending:
                entry = self._decode_fields(raw_entry)
                idle_ms = int(entry.get("time_since_delivered", 0))
                if idle_ms < min_idle_ms:
                    continue
                message_id = str(entry["message_id"])
                claimed = self.client.xclaim(
                    self.stream,
                    self.group,
                    self.consumer,
                    min_idle_ms,
                    [message_id],
                )
                if not claimed:
                    continue
                claimed_id, fields = claimed[0]
                return self._claimed_task(claimed_id, fields)

            if len(pending) < self._LEGACY_PENDING_BATCH:
                return None
            last = self._decode_fields(pending[-1])
            start = self._next_stream_id(str(last["message_id"]))

    def ack(self, message_id: str) -> None:
        self.client.xack(self.stream, self.group, message_id)

    def dead_letter(self, task: TaskEnvelope, error: str) -> None:
        fields = task.to_fields()
        fields["error"] = error[:1000]
        self.client.xadd(self.dead_letter_stream, fields)

    def heartbeat(self, metadata: Mapping[str, str], *, ttl_seconds: int = 60) -> None:
        self.client.set(
            self.heartbeat_key,
            json.dumps(dict(metadata), ensure_ascii=False),
            ex=ttl_seconds,
        )


class InMemoryTaskQueue:
    """Deterministic queue used by tests and direct embedding applications."""

    def __init__(self):
        self.ready: list[ClaimedTask] = []
        self.pending: dict[str, ClaimedTask] = {}
        self.dead: list[tuple[TaskEnvelope, str]] = []
        self.heartbeats: list[dict[str, str]] = []
        self._sequence = 0

    def publish(self, task: TaskEnvelope) -> str:
        task.validate()
        self._sequence += 1
        message_id = str(self._sequence)
        self.ready.append(ClaimedTask(message_id, task))
        return message_id

    def claim(self, *, block_ms: int = 1000) -> ClaimedTask | None:
        del block_ms
        if not self.ready:
            return None
        claimed = self.ready.pop(0)
        self.pending[claimed.message_id] = claimed
        return claimed

    def reclaim(self, *, min_idle_ms: int) -> ClaimedTask | None:
        del min_idle_ms
        return next(iter(self.pending.values()), None)

    def ack(self, message_id: str) -> None:
        self.pending.pop(message_id, None)

    def dead_letter(self, task: TaskEnvelope, error: str) -> None:
        self.dead.append((task, error))

    def heartbeat(self, metadata: Mapping[str, str], *, ttl_seconds: int = 60) -> None:
        del ttl_seconds
        self.heartbeats.append(dict(metadata))


@dataclass(slots=True)
class TaskWorker:
    queue: TaskQueue
    durable_store: DurableTaskStore
    handler: Callable[[TaskEnvelope], Mapping[str, Any]]
    worker_id: str
    provenance: Mapping[str, Any]
    validator: Callable[[TaskEnvelope], None] | None = None
    max_attempts: int = 3

    def run_once(self, *, reclaim_idle_ms: int | None = None) -> str:
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

        if self.durable_store.has_result(task.idempotency_key):
            self.queue.ack(claimed.message_id)
            return "duplicate"

        try:
            result = self.handler(task)
            inserted = self.durable_store.write_result(task, result, self.provenance)
            self.queue.ack(claimed.message_id)
            return "completed" if inserted else "duplicate"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.durable_store.write_failure(task, error, self.provenance)
            if task.attempt >= self.max_attempts:
                self.queue.dead_letter(task, error)
                self.queue.ack(claimed.message_id)
                return "dead-letter"
            return "retry"


def durable_store_from_settings(settings: Any, *, run_id: str) -> DurableTaskStore:
    if settings.data_backend == "mongodb":
        if not settings.mongo_url:
            raise ValueError("MongoDB task store requires LACLAUGPT_MONGODB_URI")
        return MongoTaskStore(
            settings.mongo_url,
            database=settings.mongo_database,
            results_collection=settings.distributed_namespace.mongo_collection("analyzed"),
            failures_collection=settings.distributed_namespace.mongo_collection("processing"),
            project_id=settings.project_id,
            run_id=run_id,
        )
    return SqliteTaskStore(settings.data_path("task_queue.sqlite3"))


def redis_queue_from_settings(settings: Any, *, run_id: str, worker_id: str) -> TaskQueue:
    if settings.cache_backend != "redis":
        raise ValueError("distributed task queue requires Redis cache backend")
    if not settings.redis_url:
        raise ValueError("Redis task queue requires LACLAUGPT_REDIS_URL")
    stream = settings.distributed_namespace.redis_key("analysis", run_id, "tasks")
    group = settings.distributed_namespace.redis_key("analysis", run_id, "workers")
    heartbeat = settings.distributed_namespace.redis_key("analysis", run_id, "worker", worker_id)
    return RedisStreamQueue(
        settings.redis_url,
        stream=stream,
        group=group,
        consumer=worker_id,
        dead_letter_stream=settings.distributed_namespace.redis_key("analysis", run_id, "dead"),
        heartbeat_key=heartbeat,
    )
