"""Redis Streams task transport.

A consumer group gives at-most-once *claiming* with at-least-once *delivery*:
a claimed entry stays in the group's pending list until it is acknowledged, so a
worker that dies mid-analysis leaves work that another consumer can reclaim.

Redis 6.0 lacks ``XAUTOCLAIM`` and the ``XPENDING IDLE`` filter introduced in
7.0. Those servers are still supported through the fallback paths below, which
is why the compatibility checks inspect the server's error message instead of a
client-side capability flag.
"""

from __future__ import annotations

import json
import time
from typing import Any, Mapping

from ..storage import redis_client
from .models import ClaimedTask, TaskEnvelope


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
        self.redis = redis_client(url)
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
