from __future__ import annotations

import json

import pytest

from laclaugpt_data_analysis.task_queue import RedisStreamQueue, TaskEnvelope


def _task_fields(*, as_bytes: bool = False):
    task = TaskEnvelope(
        task_id="task-1",
        idempotency_key="analysis:record-1:v1",
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref="mongodb://laclaugpt/ai26__raw/source-1",
        schema_version="1",
        config_revision="cfg-abc",
        codebook_revision="cb-def",
    )
    fields = {"task": json.dumps(task.to_dict())}
    if not as_bytes:
        return fields
    return {key.encode(): value.encode() for key, value in fields.items()}


def _queue(client) -> RedisStreamQueue:
    queue = object.__new__(RedisStreamQueue)
    queue.redis = client
    queue.stream = "stream"
    queue.group = "group"
    queue.consumer = "consumer"
    queue.dead_letter_stream = "stream:dead"
    queue.heartbeat_key = "stream:worker:consumer"
    return queue


class Redis60Client:
    def __init__(self, pending):
        self.pending = list(pending)
        self.pending_calls = []
        self.claim_calls = []

    def xautoclaim(self, *args, **kwargs):
        raise RuntimeError("unknown command `XAUTOCLAIM`, with args beginning with: stream")

    def xpending_range(self, stream, group, *, min, max, count, **kwargs):
        self.pending_calls.append((stream, group, min, max, count))
        if min == "-":
            return self.pending[:count]
        start_index = next(
            (index for index, item in enumerate(self.pending) if item["message_id"] == min),
            len(self.pending),
        )
        return self.pending[start_index : start_index + count]

    def xclaim(self, stream, group, consumer, min_idle_ms, message_ids):
        self.claim_calls.append((stream, group, consumer, min_idle_ms, message_ids))
        return [(message_ids[0].encode(), _task_fields(as_bytes=True))]


def test_reclaim_falls_back_to_redis_60_xpending_and_xclaim() -> None:
    client = Redis60Client(
        [
            {"message_id": "1-0", "consumer": "old", "time_since_delivered": 100, "times_delivered": 1},
            {"message_id": "2-0", "consumer": "old", "time_since_delivered": 6000, "times_delivered": 1},
        ]
    )
    queue = _queue(client)

    claimed = queue.reclaim(min_idle_ms=5000)

    assert claimed is not None
    assert claimed.message_id == "2-0"
    assert claimed.task.task_id == "task-1"
    assert client.claim_calls == [("stream", "group", "consumer", 5000, ["2-0"])]
    assert client.pending_calls[0] == ("stream", "group", "-", "+", 100)


def test_reclaim_legacy_returns_none_when_no_entry_is_idle_enough() -> None:
    client = Redis60Client(
        [{"message_id": "1-0", "consumer": "old", "time_since_delivered": 100, "times_delivered": 1}]
    )
    queue = _queue(client)

    assert queue.reclaim(min_idle_ms=5000) is None
    assert client.claim_calls == []


def test_reclaim_legacy_paginates_without_xpending_idle_filter() -> None:
    pending = [
        {
            "message_id": f"1-{index}",
            "consumer": "old",
            "time_since_delivered": 100,
            "times_delivered": 1,
        }
        for index in range(100)
    ]
    pending.append(
        {"message_id": "1-100", "consumer": "old", "time_since_delivered": 6000, "times_delivered": 1}
    )
    client = Redis60Client(pending)
    queue = _queue(client)

    claimed = queue.reclaim(min_idle_ms=5000)

    assert claimed is not None
    assert claimed.message_id == "1-100"
    assert len(client.pending_calls) == 2
    assert client.pending_calls[1][2] == "1-100"


def test_reclaim_propagates_non_compatibility_errors() -> None:
    class BrokenClient:
        def xautoclaim(self, *args, **kwargs):
            raise RuntimeError("connection reset")

    queue = _queue(BrokenClient())

    with pytest.raises(RuntimeError, match="connection reset"):
        queue.reclaim(min_idle_ms=5000)


def test_xautoclaim_path_also_decodes_byte_payloads() -> None:
    class ModernClient:
        def xautoclaim(self, *args, **kwargs):
            return ("0-0", [(b"9-0", _task_fields(as_bytes=True))])

    queue = _queue(ModernClient())

    claimed = queue.reclaim(min_idle_ms=5000)

    assert claimed is not None
    assert claimed.message_id == "9-0"
    assert claimed.task.record_ref.endswith("source-1")


def test_reclaim_falls_back_when_redis_raises_responserror() -> None:
    """Issue #159: real Redis reports XAUTOCLAIM as a ``ResponseError``.

    ``Redis60Client`` above raises ``RuntimeError``, which the original
    ``except RuntimeError`` clause caught — so the compatibility path was tested
    with an exception class the server never actually raises. Real Redis 6.0
    raises ``redis.exceptions.ResponseError``, which derives only from
    ``RedisError`` and is **not** a ``RuntimeError``/``TypeError``/
    ``AttributeError``. The fallback therefore never ran in production.
    """
    from redis.exceptions import ResponseError

    class RealRedis60Client(Redis60Client):
        def xautoclaim(self, *args, **kwargs):
            raise ResponseError(
                "unknown command `XAUTOCLAIM`, with args beginning with: stream"
            )

    pending = [
        {"message_id": "1-100", "consumer": "old", "time_since_delivered": 6000, "times_delivered": 1}
    ]
    client = RealRedis60Client(pending)
    queue = _queue(client)

    claimed = queue.reclaim(min_idle_ms=5000)

    assert claimed is not None, "the Redis 6 fallback must run for ResponseError"
    assert claimed.message_id == "1-100"
    assert client.claim_calls, "XCLAIM must have been used as the fallback"


def test_responserror_is_not_a_runtimeerror() -> None:
    """Documents why the class-based guard was wrong."""
    from redis.exceptions import RedisError, ResponseError

    assert issubclass(ResponseError, RedisError)
    assert not issubclass(ResponseError, RuntimeError)
    assert not issubclass(ResponseError, TypeError)
    assert not issubclass(ResponseError, AttributeError)


def test_non_compatibility_responserror_still_propagates() -> None:
    """A genuine Redis error must not be swallowed by the fallback."""
    from redis.exceptions import ResponseError

    class BrokenClient:
        def xautoclaim(self, *args, **kwargs):
            raise ResponseError("WRONGTYPE Operation against a key holding the wrong kind of value")

    queue = _queue(BrokenClient())
    with pytest.raises(ResponseError):
        queue.reclaim(min_idle_ms=5000)
