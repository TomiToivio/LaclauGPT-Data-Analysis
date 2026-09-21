"""Distributed task queue contracts and adapters for LaclauGPT analysis."""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .config import Settings

FAILURE_RESPONSE_RAW_MAX_CHARS = 16_384


def bounded_failure_diagnostics(
    diagnostics: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Normalize and bound model-output diagnostics before durable persistence."""
    if not diagnostics:
        return {}
    raw = str(diagnostics.get("response_raw") or "")
    finish_reason = str(diagnostics.get("finish_reason") or "")
    if not raw and not finish_reason:
        return {}
    return {
        "response_raw": raw[:FAILURE_RESPONSE_RAW_MAX_CHARS],
        "response_raw_chars": len(raw),
        "response_raw_truncated": len(raw) > FAILURE_RESPONSE_RAW_MAX_CHARS,
        "finish_reason": finish_reason,
        "diagnostic_only": True,
    }


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
            raise ValueError("task envelope missing required fields: " + ", ".join(missing))
        if self.attempt < 1:
            raise ValueError("task envelope attempt must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TaskEnvelope:
        envelope = cls(
            task_id=str(payload.get("task_id") or ""),
            idempotency_key=str(payload.get("idempotency_key") or ""),
            project_id=str(payload.get("project_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            task_type=str(payload.get("task_type") or ""),
            record_ref=str(payload.get("record_ref") or ""),
            schema_version=str(payload.get("schema_version") or ""),
            config_revision=str(payload.get("config_revision") or ""),
            codebook_revision=str(payload.get("codebook_revision") or ""),
            attempt=int(payload.get("attempt") or 1),
        )
        envelope.validate()
        return envelope


@dataclass(frozen=True, slots=True)
class ClaimedTask:
    message_id: str
    task: TaskEnvelope


class TaskQueue(Protocol):
    def publish(self, task: TaskEnvelope) -> str: ...

    def claim(self) -> ClaimedTask | None: ...

    def reclaim(self, *, min_idle_ms: int) -> ClaimedTask | None: ...

    def ack(self, message_id: str) -> None: ...

    def dead_letter(self, task: TaskEnvelope, error: str) -> None: ...

    def heartbeat(self, **fields: str) -> None: ...


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
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None: ...


class InMemoryTaskQueue:
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
    def __init__(self) -> None:
        self.results: dict[str, dict[str, Any]] = {}
        self.failures: list[dict[str, Any]] = []

    def has_result(self, idempotency_key: str) -> bool:
        return idempotency_key in self.results

    def write_result(
        self,
        task: TaskEnvelope,
        result: Mapping[str, Any],
        provenance: Mapping[str, Any],
    ) -> bool:
        if task.idempotency_key in self.results:
            return False
        self.results[task.idempotency_key] = {
            "task": task.to_dict(),
            "result": dict(result),
            "provenance": dict(provenance),
        }
        return True

    def write_failure(
        self,
        task: TaskEnvelope,
        error: str,
        provenance: Mapping[str, Any],
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        self.failures.append(
            {
                "task": task.to_dict(),
                "error": error,
                "provenance": dict(provenance),
                **bounded_failure_diagnostics(diagnostics),
            }
        )


class SqliteTaskStore:
    """Durable local task result/failure history for direct and offline operation."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS task_results ("
                "idempotency_key TEXT PRIMARY KEY, source_url TEXT, result_json TEXT NOT NULL, "
                "provenance_json TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            result_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(task_results)")
            }
            if "source_url" not in result_columns:
                connection.execute("ALTER TABLE task_results ADD COLUMN source_url TEXT")

            connection.execute(
                "CREATE TABLE IF NOT EXISTS task_failures ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, "
                "idempotency_key TEXT NOT NULL, source_url TEXT, attempt INTEGER NOT NULL, "
                "error TEXT NOT NULL, provenance_json TEXT NOT NULL, response_raw TEXT, "
                "response_raw_chars INTEGER, response_raw_truncated INTEGER, finish_reason TEXT, "
                "diagnostic_only INTEGER, created_at REAL NOT NULL)"
            )
            failure_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(task_failures)")
            }
            if "source_url" not in failure_columns:
                connection.execute("ALTER TABLE task_failures ADD COLUMN source_url TEXT")
            for column, declaration in {
                "response_raw": "TEXT",
                "response_raw_chars": "INTEGER",
                "response_raw_truncated": "INTEGER",
                "finish_reason": "TEXT",
                "diagnostic_only": "INTEGER",
            }.items():
                if column not in failure_columns:
                    connection.execute(
                        f"ALTER TABLE task_failures ADD COLUMN {column} {declaration}"
                    )

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
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        diagnostic = bounded_failure_diagnostics(diagnostics)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO task_failures "
                "(task_id, idempotency_key, source_url, attempt, error, provenance_json, "
                "response_raw, response_raw_chars, response_raw_truncated, finish_reason, "
                "diagnostic_only, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task.task_id,
                    task.idempotency_key,
                    task.record_ref,
                    task.attempt,
                    error,
                    json.dumps(dict(provenance), ensure_ascii=False, default=str),
                    diagnostic.get("response_raw"),
                    diagnostic.get("response_raw_chars"),
                    int(bool(diagnostic.get("response_raw_truncated"))) if diagnostic else None,
                    diagnostic.get("finish_reason"),
                    int(bool(diagnostic.get("diagnostic_only"))) if diagnostic else None,
                    time.time(),
                ),
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
        try:
            from pymongo import MongoClient
        except ImportError as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError("pymongo is required for MongoTaskStore") from exc
        client = MongoClient(mongo_url)
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
        diagnostics: Mapping[str, Any] | None = None,
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
                **bounded_failure_diagnostics(diagnostics),
                "created_at": time.time(),
            }
        )


class RedisStreamQueue:
    """Redis Streams adapter using consumer groups and pending-entry reclaim."""

    _LEGACY_PENDING_BATCH = 100
    _MAX_ENTRIES_PER_CALL = 1000

    @staticmethod
    def _is_xautoclaim_unknown_command(exc: Exception) -> bool:
        """True when the server rejected XAUTOCLAIM as an unknown command.

        Redis 6.0 does not implement XAUTOCLAIM. The server reports this as a
        ``ResponseError`` ("unknown command `XAUTOCLAIM`"), which is a ``RedisError``
        and **not** a ``RuntimeError``/``TypeError``/``AttributeError`` — so the
        compatibility fallback must inspect the message rather than rely on the
        exception class.
        """
        message = str(exc).lower()
        return "unknown command" in message and "xautoclaim" in message

    @staticmethod
    def _is_xpending_idle_unsupported(exc: Exception) -> bool:
        """True when the server rejected XPENDING's IDLE filter syntax.

        Redis 6.0 lacks the XPENDING IDLE filter added in Redis 7.0 and reports
        the unsupported form as a ResponseError, typically just "syntax error".
        Limit the compatibility fallback to that server-side syntax rejection so
        unrelated Redis failures still propagate.
        """
        return "syntax error" in str(exc).lower()

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
        except ImportError as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError("redis is required for RedisStreamQueue") from exc
        self.redis = redis.Redis.from_url(url, decode_responses=True)
        self.stream = stream
        self.group = group
        self.consumer = consumer
        self.dead_letter_stream = dead_letter_stream or f"{stream}:dead"
        self.heartbeat_key = heartbeat_key or f"{stream}:heartbeat:{consumer}"
        self.quarantined_count = 0
        try:
            self.redis.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception as exc:  # pragma: no cover - redis response type varies
            if "BUSYGROUP" not in str(exc):
                raise

    @staticmethod
    def _text(value: Any) -> str:
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    @staticmethod
    def _field(values: Mapping[Any, Any], name: str) -> Any:
        return values.get(name) if name in values else values.get(name.encode())

    @classmethod
    def _decode_task(cls, values: Mapping[Any, Any]) -> TaskEnvelope:
        raw = cls._field(values, "task")
        if raw is None:
            raise ValueError("Redis task entry is missing task payload")
        return TaskEnvelope.from_dict(json.loads(cls._text(raw)))

    @classmethod
    def _next_stream_id(cls, value: Any) -> str:
        text = cls._text(value)
        milliseconds, separator, sequence = text.rpartition("-")
        if separator and milliseconds.isdigit() and sequence.isdigit():
            return f"{milliseconds}-{int(sequence) + 1}"
        return text

    @staticmethod
    def _idle_ms(entry: Any) -> int:
        if isinstance(entry, Mapping):
            return int(entry.get("time_since_delivered", 0))
        return int(entry[2])

    def _quarantine_entry(
        self,
        message_id: Any,
        values: Mapping[Any, Any],
        error: Exception,
    ) -> None:
        entry_id = self._text(message_id)
        raw_fields = {self._text(key): self._text(value) for key, value in values.items()}
        self.redis.xadd(
            self.dead_letter_stream,
            {
                "source_message_id": entry_id,
                "error": f"{type(error).__name__}: {error}",
                "raw_fields": json.dumps(raw_fields, ensure_ascii=False, sort_keys=True),
            },
        )
        self.redis.xack(self.stream, self.group, entry_id)
        self.quarantined_count = getattr(self, "quarantined_count", 0) + 1

    def _decode_or_quarantine(
        self,
        message_id: Any,
        values: Mapping[Any, Any],
    ) -> ClaimedTask | None:
        try:
            task = self._decode_task(values)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._quarantine_entry(message_id, values, exc)
            return None
        return ClaimedTask(self._text(message_id), task)

    def publish(self, task: TaskEnvelope) -> str:
        payload = json.dumps(task.to_dict())
        # Keep the write boundary strict: anything published must round-trip
        # through the same decoder used by workers.
        self._decode_task({"task": payload})
        return self._text(self.redis.xadd(self.stream, {"task": payload}))

    def claim(self) -> ClaimedTask | None:
        examined = 0
        while examined < self._MAX_ENTRIES_PER_CALL:
            response = self.redis.xreadgroup(
                self.group,
                self.consumer,
                {self.stream: ">"},
                count=1,
                block=1000,
            )
            if not response:
                return None
            _, entries = response[0]
            if not entries:
                return None
            message_id, values = entries[0]
            examined += 1
            claimed = self._decode_or_quarantine(message_id, values)
            if claimed is not None:
                return claimed
        return None

    def reclaim(self, *, min_idle_ms: int) -> ClaimedTask | None:
        examined = 0
        cursor = "0-0"
        xautoclaim_supported = True
        while examined < self._MAX_ENTRIES_PER_CALL:
            try:
                response = self.redis.xautoclaim(
                    self.stream,
                    self.group,
                    self.consumer,
                    min_idle_ms,
                    cursor,
                    count=1,
                )
            except (AttributeError, TypeError):
                # Very old client libraries without the xautoclaim method.
                xautoclaim_supported = False
                break
            except Exception as exc:
                if not self._is_xautoclaim_unknown_command(exc):
                    raise
                xautoclaim_supported = False
                break

            entries = response[1] if response and len(response) > 1 else []
            if not entries:
                return None
            next_cursor = self._text(response[0]) if response else "0-0"
            message_id, values = entries[0]
            examined += 1
            claimed = self._decode_or_quarantine(message_id, values)
            if claimed is not None:
                return claimed
            cursor = next_cursor if next_cursor != "0-0" else self._next_stream_id(message_id)

        if xautoclaim_supported:
            return None

        start = "-"
        while examined < self._MAX_ENTRIES_PER_CALL:
            request_count = min(
                self._LEGACY_PENDING_BATCH,
                self._MAX_ENTRIES_PER_CALL - examined,
            )
            try:
                pending = self.redis.xpending_range(
                    self.stream,
                    self.group,
                    min=start,
                    max="+",
                    count=request_count,
                    idle=min_idle_ms,
                )
            except TypeError:
                pending = self.redis.xpending_range(
                    self.stream,
                    self.group,
                    min=start,
                    max="+",
                    count=request_count,
                )
            except Exception as exc:
                if not self._is_xpending_idle_unsupported(exc):
                    raise
                pending = self.redis.xpending_range(
                    self.stream,
                    self.group,
                    min=start,
                    max="+",
                    count=request_count,
                )
            examined += len(pending)
            eligible = [entry for entry in pending if self._idle_ms(entry) >= min_idle_ms]
            if eligible:
                entry = eligible[0]
                message_id = entry["message_id"] if isinstance(entry, dict) else entry[0]
                claimed_entries = self.redis.xclaim(
                    self.stream,
                    self.group,
                    self.consumer,
                    min_idle_ms,
                    [message_id],
                )
                if not claimed_entries:
                    return None
                claimed_id, values = claimed_entries[0]
                claimed = self._decode_or_quarantine(claimed_id, values)
                if claimed is not None:
                    return claimed
                start = self._next_stream_id(claimed_id)
                continue
            if not pending or len(pending) < request_count:
                return None
            last = pending[-1]
            last_id = last["message_id"] if isinstance(last, dict) else last[0]
            start = self._next_stream_id(last_id)
        return None

    def ack(self, message_id: str) -> None:
        self.redis.xack(self.stream, self.group, message_id)

    def dead_letter(self, task: TaskEnvelope, error: str) -> None:
        self.redis.xadd(
            self.dead_letter_stream,
            {"task": json.dumps(task.to_dict()), "error": error},
        )

    def heartbeat(self, **fields: str) -> None:
        payload = {"updated_at": str(time.time()), **fields}
        self.redis.hset(self.heartbeat_key, mapping=payload)


class TaskWorker:
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
    ) -> None:
        self.queue = queue
        self.durable_store = durable_store
        self.handler = handler
        self.worker_id = worker_id
        self.provenance = dict(provenance)
        self.validator = validator
        self.max_attempts = max_attempts

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

        if self.durable_store.has_result(task.idempotency_key):
            self.queue.ack(claimed.message_id)
            return "duplicate"

        try:
            result = self.handler(task)
            inserted = self.durable_store.write_result(task, result, self.provenance)
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
    namespace = settings.distributed_namespace
    return MongoTaskStore(
        settings.mongo_url,
        database=settings.mongo_database,
        result_collection=namespace.mongo_collection("analysis_results"),
        failure_collection=namespace.mongo_collection("analysis_failures"),
        project_id=settings.project_id,
        run_id=run_id,
    )
