from __future__ import annotations

import json

import pytest

from laclaugpt_data_analysis.task_queue import RedisStreamQueue, TaskEnvelope


def _task_fields():
    task = TaskEnvelope(
        task_id="task-good",
        idempotency_key="analysis:good:v1",
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref="mongodb://laclaugpt/ai26__raw/good",
        schema_version="1",
        config_revision="cfg",
        codebook_revision="cb",
    )
    return {"task": json.dumps(task.to_dict())}


def _queue(client) -> RedisStreamQueue:
    queue = object.__new__(RedisStreamQueue)
    queue.redis = client
    queue.stream = "stream"
    queue.group = "group"
    queue.consumer = "consumer"
    queue.dead_letter_stream = "stream:dead"
    queue.heartbeat_key = "stream:heartbeat:consumer"
    queue.quarantined_count = 0
    return queue


class QuarantineMixin:
    def __init__(self):
        self.dead = []
        self.acked = []

    def xadd(self, stream, fields):
        self.dead.append((stream, fields))
        return "dead-1"

    def xack(self, stream, group, message_id):
        self.acked.append((stream, group, message_id))
        return 1


def _assert_quarantined(client, message_id: str) -> None:
    assert client.acked == [("stream", "group", message_id)]
    assert len(client.dead) == 1
    stream, fields = client.dead[0]
    assert stream == "stream:dead"
    assert fields["source_message_id"] == message_id
    assert "missing task payload" in fields["error"]
    assert json.loads(fields["raw_fields"]) == {"task_id": "legacy-bad"}


def test_claim_quarantines_malformed_entry_and_continues() -> None:
    class Client(QuarantineMixin):
        def __init__(self):
            super().__init__()
            self.responses = [
                [("stream", [("1-0", {"task_id": "legacy-bad"})])],
                [("stream", [("2-0", _task_fields())])],
            ]

        def xreadgroup(self, *args, **kwargs):
            return self.responses.pop(0)

    client = Client()
    queue = _queue(client)

    claimed = queue.claim()

    assert claimed is not None
    assert claimed.message_id == "2-0"
    assert claimed.task.task_id == "task-good"
    assert queue.quarantined_count == 1
    _assert_quarantined(client, "1-0")


def test_reclaim_xautoclaim_quarantines_head_and_continues() -> None:
    class Client(QuarantineMixin):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def xautoclaim(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return ("2-0", [("1-0", {"task_id": "legacy-bad"})])
            return ("0-0", [("2-0", _task_fields())])

    client = Client()
    queue = _queue(client)

    claimed = queue.reclaim(min_idle_ms=5000)

    assert claimed is not None
    assert claimed.message_id == "2-0"
    assert claimed.task.task_id == "task-good"
    assert client.calls == 2
    assert queue.quarantined_count == 1
    _assert_quarantined(client, "1-0")


def test_reclaim_legacy_fallback_quarantines_head_and_continues() -> None:
    class Client(QuarantineMixin):
        def __init__(self):
            super().__init__()
            self.pending = [
                {
                    "message_id": "1-0",
                    "consumer": "old",
                    "time_since_delivered": 6000,
                    "times_delivered": 1,
                },
                {
                    "message_id": "2-0",
                    "consumer": "old",
                    "time_since_delivered": 6000,
                    "times_delivered": 1,
                },
            ]

        def xautoclaim(self, *args, **kwargs):
            raise RuntimeError("unknown command `XAUTOCLAIM`")

        def xpending_range(self, stream, group, *, min, max, count, **kwargs):
            if min == "-":
                return self.pending[:count]
            return [entry for entry in self.pending if entry["message_id"] >= min][:count]

        def xclaim(self, stream, group, consumer, min_idle_ms, message_ids):
            if message_ids[0] == "1-0":
                return [("1-0", {"task_id": "legacy-bad"})]
            return [("2-0", _task_fields())]

    client = Client()
    queue = _queue(client)

    claimed = queue.reclaim(min_idle_ms=5000)

    assert claimed is not None
    assert claimed.message_id == "2-0"
    assert claimed.task.task_id == "task-good"
    assert queue.quarantined_count == 1
    _assert_quarantined(client, "1-0")


def test_reclaim_quarantine_scan_is_bounded() -> None:
    class Client(QuarantineMixin):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def xautoclaim(self, *args, **kwargs):
            self.calls += 1
            message_id = f"{self.calls}-0"
            return (
                f"{self.calls + 1}-0",
                [(message_id, {"task_id": "legacy-bad"})],
            )

    client = Client()
    queue = _queue(client)
    queue._MAX_ENTRIES_PER_CALL = 3

    assert queue.reclaim(min_idle_ms=5000) is None
    assert client.calls == 3
    assert queue.quarantined_count == 3
    assert len(client.dead) == 3
    assert len(client.acked) == 3


def test_publish_fails_closed_when_round_trip_decode_rejects(monkeypatch) -> None:
    class Client:
        def xadd(self, *args, **kwargs):
            raise AssertionError("xadd must not run after failed validation")

    queue = _queue(Client())
    task = TaskEnvelope(
        task_id="task-1",
        idempotency_key="analysis:1:v1",
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref="mongodb://laclaugpt/ai26__raw/1",
        schema_version="1",
        config_revision="cfg",
        codebook_revision="cb",
    )

    def reject(cls, values):
        raise ValueError("round-trip rejected")

    monkeypatch.setattr(RedisStreamQueue, "_decode_task", classmethod(reject))

    with pytest.raises(ValueError, match="round-trip rejected"):
        queue.publish(task)
