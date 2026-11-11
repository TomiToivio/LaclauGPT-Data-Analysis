"""The oldest ready documents must be reachable, not merely sorted (#429).

`seed_ready_tasks` walked the ready frame in one order — `(source_priority, published_at DESC,
source_url)` — and stopped as soon as the cycle's budget was spent. That is correct for keeping the
live tiers fresh and structurally unable to reach the tail: on 2026-11-11, 416 non-X ready documents
had never been analysed (307 Bluesky, 295 of them published in October) while the walk consumed all
ten slots inside the P1 tier every cycle and never moved past position ~2,130.

The fix is a reserved slice of the budget that reads the same frame **oldest-first**, so the pool
drains at a known rate instead of never. These tests pin the four things that can go wrong with that
idea: the slice starving the fresh work, the slice exceeding the budget, the slice counting work that
was already done, and the slice silently disappearing when a handoff reader cannot serve it.
"""
from __future__ import annotations

import pytest

from laclaugpt_data_analysis.distributed_worker import seed_ready_tasks


class Task:
    def __init__(self, key: str) -> None:
        self.idempotency_key = key


class Binding:
    class Manifest:
        run_id = "ai26-distributed-001"

    manifest = Manifest()

    def task_from_handoff(self, envelope):
        return Task(str(envelope["handoff_key"]))


class Queue:
    def __init__(self) -> None:
        self.published: list[str] = []

    def publish(self, task) -> None:
        self.published.append(task.idempotency_key)


class Durable:
    def __init__(self) -> None:
        self.completed: set[str] = set()
        self.terminal: set[str] = set()

    def has_result(self, key: str, fingerprint: str = "") -> bool:
        return key in self.completed

    def has_terminal_failure(self, key: str) -> bool:
        return key in self.terminal

    def rearm_terminal_failure(self, key: str) -> int:
        return 0


def handoff(key: str, *, priority: int, published_at: str) -> dict:
    return {
        "handoff_key": key,
        "run_id": "ai26-distributed-001",
        "source_priority": priority,
        "published_at": published_at,
        "source_url": f"https://example.invalid/{key}",
    }


class Frame:
    """The ready frame with the real ordering rule, and the two ways to read it."""

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def ready_handoffs(self, run_id: str, *, limit: int, offset: int = 0):
        ordered = sorted(
            self.rows,
            key=lambda row: (row["source_priority"], _neg(row["published_at"]), row["source_url"]),
        )
        return ordered[offset : offset + limit]

    def oldest_ready_handoffs(self, run_id: str, *, limit: int, offset: int = 0):
        ordered = sorted(self.rows, key=lambda row: (row["published_at"], row["source_url"]))
        return ordered[offset : offset + limit]


def _neg(stamp: str) -> str:
    """Descending by string without parsing: invert each character code."""
    return "".join(chr(0x10FFFF - ord(ch)) for ch in stamp)


def frame_with_fresh_p1_and_old_p2(p1: int = 10, p2: int = 5) -> Frame:
    rows = [
        handoff(f"p1-{index:02d}", priority=1, published_at=f"2026-11-11T{index // 6:02d}:00:00Z")
        for index in range(p1)
    ]
    rows += [
        handoff(f"p2-{index:02d}", priority=2, published_at=f"2026-10-{index + 1:02d}T00:00:00Z")
        for index in range(p2)
    ]
    return Frame(rows)


def seed(frame, *, limit: int, backfill: int, durable: Durable | None = None):
    diagnostics: dict = {}
    queue = Queue()
    published = seed_ready_tasks(
        Binding(),
        frame,
        queue,
        durable or Durable(),
        limit=limit,
        backfill_limit=backfill,
        diagnostics=diagnostics,
    )
    assert published == len(queue.published)
    return published, queue.published, diagnostics


def test_priority_order_alone_leaves_the_old_tier_unreachable():
    """The defect as it happened: ten fresh P1 documents consume a ten-slot cycle, every cycle."""
    published, keys, diagnostics = seed(frame_with_fresh_p1_and_old_p2(), limit=10, backfill=0)

    assert published == 10
    assert all(key.startswith("p1-") for key in keys)
    assert not any(key.startswith("p2-") for key in keys)
    assert diagnostics["backfill_published"] == 0


def test_a_reserved_slice_reaches_the_oldest_documents_first():
    published, keys, diagnostics = seed(frame_with_fresh_p1_and_old_p2(), limit=10, backfill=3)

    assert published == 10
    # The two oldest documents in the whole frame are October P2 records; they go first.
    assert keys[:2] == ["p2-00", "p2-01"], keys
    assert diagnostics["backfill_published"] == 3
    assert diagnostics["backfill_oldest_published_at"].startswith("2026-10-01")
    assert diagnostics["examined"] == 10, "the priority pass still fills the rest of the budget"


def test_the_slice_cannot_exceed_the_cycle_budget():
    published, keys, diagnostics = seed(frame_with_fresh_p1_and_old_p2(), limit=4, backfill=9)

    assert published == 4
    assert len(keys) == 4
    assert diagnostics["backfill_limit"] == 4
    assert diagnostics["backfill_published"] == 4


def test_the_slice_skips_work_that_is_already_done():
    durable = Durable()
    durable.completed.update({"p2-00", "p2-01"})
    durable.terminal.update({"p2-02"})

    published, keys, diagnostics = seed(
        frame_with_fresh_p1_and_old_p2(), limit=10, backfill=2, durable=durable
    )

    assert published == 10
    assert keys[:2] == ["p2-03", "p2-04"], "the oldest *unanalysed* documents, not the oldest rows"
    assert diagnostics["already_analyzed"] >= 2
    assert diagnostics["backfill_published"] == 2


def test_backfill_zero_restores_the_pure_priority_order():
    """The escape hatch has to be honest: 0 means the old behaviour, not a silent default."""
    _, keys, diagnostics = seed(frame_with_fresh_p1_and_old_p2(), limit=10, backfill=0)

    assert diagnostics["backfill_limit"] == 0
    assert diagnostics["backfill_examined"] == 0
    assert "backfill_published" in diagnostics


def test_a_reader_without_oldest_first_does_not_break_the_cycle(caplog):
    class PriorityOnly:
        def __init__(self, rows):
            self.rows = rows

        def ready_handoffs(self, run_id, *, limit, offset=0):
            return sorted(
                self.rows, key=lambda row: (row["source_priority"], _neg(row["published_at"]))
            )[offset : offset + limit]

    frame = PriorityOnly(frame_with_fresh_p1_and_old_p2().rows)

    published, keys, diagnostics = seed(frame, limit=10, backfill=3)

    assert published == 10, "a missing backfill reader degrades to the old order, it does not crash"
    assert diagnostics["backfill_published"] == 0
    assert any("cannot walk the frame oldest-first" in record.message for record in caplog.records)


def test_both_passes_together_never_exceed_the_budget():
    for limit, backfill in ((1, 1), (3, 1), (10, 10), (10, 0)):
        published, keys, _ = seed(frame_with_fresh_p1_and_old_p2(), limit=limit, backfill=backfill)
        assert published == len(keys) <= limit


def test_the_drain_is_deterministic():
    first = seed(frame_with_fresh_p1_and_old_p2(), limit=10, backfill=3)[1]
    second = seed(frame_with_fresh_p1_and_old_p2(), limit=10, backfill=3)[1]
    assert first == second


def test_an_idle_frame_reports_no_backfill_instead_of_failing():
    published, keys, diagnostics = seed(Frame([]), limit=10, backfill=3)

    assert published == 0 and keys == []
    assert diagnostics["backfill_published"] == 0
    assert diagnostics["backfill_examined"] == 0


@pytest.mark.parametrize("backfill", [-2, 0])
def test_a_negative_slice_is_treated_as_off(backfill):
    published, keys, diagnostics = seed(frame_with_fresh_p1_and_old_p2(), limit=4, backfill=backfill)
    assert published == 4
    assert diagnostics["backfill_limit"] == 0
