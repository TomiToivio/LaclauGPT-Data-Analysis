"""The reserved backfill slice must be able to skip a closed stratum (#433).

`seed_ready_tasks` reserves part of the cycle budget for the oldest never-analysed documents (#429) and
walks the ready frame oldest-first. The X capture stopped on 2026-10-26, so the X stratum reaches further
back in publication time than every live stratum, and the reserved slice was spent there: in the 24 h to
2026-11-12 15:37 EET, 29 of 30 backfill completions were X documents published 2026-09-01/02, while the
non-X tail the slice was created for grew 416 -> 439.

These tests pin the opt-in exclusion that makes that pool reachable:

* the query builder turns an exclusion into `source.platform: {$nin: [...]}` and composes it with the
  existing single-platform scope;
* the default (no exclusion configured) is byte-for-byte the pre-#433 query and the pre-#433 walk, so
  nothing changes until somebody names a closed platform;
* a configured exclusion actually reaches the non-X tail in the same number of slots;
* a handoff reader that cannot skip a platform does not crash the cycle — it keeps its old ordering and
  says so.
"""
from __future__ import annotations

import pytest

from laclaugpt_data_analysis.distributed_worker import (
    _accepts_keyword,
    ready_handoff_query,
    seed_ready_tasks,
)

# ---------------------------------------------------------------- query builder

def test_no_exclusion_leaves_the_query_untouched():
    query = ready_handoff_query(project_id="ai26", run_id="ai26-distributed-001")
    assert "source.platform" not in query


def test_single_platform_scope_is_unchanged():
    query = ready_handoff_query(project_id="ai26", platform="bluesky")
    assert query["source.platform"] == "bluesky"


def test_exclusion_alone_becomes_nin():
    query = ready_handoff_query(project_id="ai26", exclude_platforms=["x"])
    assert query["source.platform"] == {"$nin": ["x"]}


def test_exclusion_composes_with_a_platform_scope():
    query = ready_handoff_query(project_id="ai26", platform="bluesky", exclude_platforms=["x"])
    assert query["source.platform"] == {"$in": ["bluesky"], "$nin": ["x"]}


def test_blank_exclusions_are_ignored():
    query = ready_handoff_query(project_id="ai26", exclude_platforms=["", "  "])
    assert "source.platform" not in query


# ---------------------------------------------------------------- the walk itself

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
    def has_result(self, key: str, fingerprint: str = "") -> bool:
        return False

    def has_terminal_failure(self, key: str) -> bool:
        return False

    def rearm_terminal_failure(self, key: str) -> int:
        return 0


def handoff(key: str, *, platform: str, priority: int, published_at: str) -> dict:
    return {
        "handoff_key": key,
        "run_id": "ai26-distributed-001",
        "source_platform": platform,
        "platform": platform,
        "source_priority": priority,
        "published_at": published_at,
        "source_url": f"https://example.invalid/{key}",
    }


class Frame:
    """A ready frame whose oldest-first reader honours (or ignores) an exclusion."""

    def __init__(self, rows: list[dict], *, supports_exclusion: bool = True) -> None:
        self.rows = rows
        self.supports_exclusion = supports_exclusion

    def ready_handoffs(self, run_id: str, *, limit: int, offset: int = 0):
        ordered = sorted(self.rows, key=lambda row: row["published_at"], reverse=True)
        return ordered[offset : offset + limit]

    def oldest_ready_handoffs(self, run_id: str, *, limit: int, offset: int = 0, **kwargs):
        rows = self.rows
        if self.supports_exclusion:
            excluded = set(kwargs.get("exclude_platforms") or [])
            rows = [row for row in rows if row["platform"] not in excluded]
        elif kwargs.get("exclude_platforms"):
            raise AssertionError("the exclusion must not be passed to a reader that cannot honour it")
        ordered = sorted(rows, key=lambda row: (row["published_at"], row["source_url"]))
        return ordered[offset : offset + limit]


class LegacyFrame(Frame):
    """The pre-#433 reader signature: no `exclude_platforms` keyword at all."""

    def oldest_ready_handoffs(self, run_id: str, *, limit: int, offset: int = 0):
        ordered = sorted(self.rows, key=lambda row: (row["published_at"], row["source_url"]))
        return ordered[offset : offset + limit]


def closed_x_stratum() -> list[dict]:
    return [
        handoff(f"x-{index:02d}", platform="x", priority=3, published_at=f"2026-09-{index + 1:02d}T00:00:00Z")
        for index in range(10)
    ]


def live_tail() -> list[dict]:
    return [
        handoff(f"bluesky-{index:02d}", platform="bluesky", priority=1,
                published_at=f"2026-10-{index + 10:02d}T00:00:00Z")
        for index in range(5)
    ]


def seed(frame, *, limit: int, backfill: int, exclude: list[str] | None = None):
    diagnostics: dict = {}
    queue = Queue()
    published = seed_ready_tasks(
        Binding(),
        frame,
        queue,
        Durable(),
        limit=limit,
        backfill_limit=backfill,
        backfill_exclude_platforms=exclude,
        diagnostics=diagnostics,
    )
    assert published == len(queue.published)
    return published, queue.published, diagnostics


def test_without_an_exclusion_the_closed_stratum_still_fills_the_slice():
    """Pins the #433 symptom, so the fix cannot be mistaken for a change of default."""
    frame = Frame(closed_x_stratum() + live_tail())
    _, published, diagnostics = seed(frame, limit=4, backfill=1)
    assert diagnostics["backfill_published"] == 1
    assert published[0].startswith("x-")


def test_an_exclusion_reaches_the_non_x_tail_in_the_same_slots():
    frame = Frame(closed_x_stratum() + live_tail())
    _, published, diagnostics = seed(frame, limit=4, backfill=1, exclude=["x"])
    assert diagnostics["backfill_published"] == 1
    assert published[0] == "bluesky-00", "the reserved slice must reach the live tail, not September X"
    assert diagnostics["backfill_excluded_platforms"] == 1


def test_the_priority_walk_is_not_affected_by_the_exclusion():
    """Only the reserved slice skips the stratum; keeping the live tiers fresh is unchanged."""
    frame = Frame(closed_x_stratum() + live_tail())
    published, queue, _ = seed(frame, limit=10, backfill=2, exclude=["x"])
    assert published == 10
    # the priority walk still sees everything, including X
    assert any(key.startswith("x-") for key in queue[2:])


def test_a_reader_without_exclusion_support_keeps_its_old_ordering(caplog):
    """An alternative handoff implementation must not crash the cycle (#433 safety)."""
    frame = LegacyFrame(closed_x_stratum() + live_tail())
    assert not _accepts_keyword(frame.oldest_ready_handoffs, "exclude_platforms")
    with caplog.at_level("WARNING"):
        _, published, diagnostics = seed(frame, limit=4, backfill=1, exclude=["x"])
    assert diagnostics["backfill_published"] == 1
    assert published[0].startswith("x-")
    assert any("cannot skip a platform" in record.message for record in caplog.records)


def test_reader_signature_detection():
    frame = Frame([])

    def with_kwarg(run_id, *, limit, offset=0, exclude_platforms=None):
        return []

    def with_kwargs(run_id, **kwargs):
        return []

    def without(run_id, *, limit, offset=0):
        return []

    assert _accepts_keyword(with_kwarg, "exclude_platforms")
    assert _accepts_keyword(with_kwargs, "exclude_platforms")
    assert not _accepts_keyword(without, "exclude_platforms")
    assert _accepts_keyword(frame.oldest_ready_handoffs, "exclude_platforms")


@pytest.mark.parametrize("exclude", [None, [], ["  "]])
def test_no_configured_exclusion_means_no_exclusion(exclude):
    frame = Frame(closed_x_stratum() + live_tail())
    _, published, diagnostics = seed(frame, limit=4, backfill=1, exclude=exclude)
    assert published[0].startswith("x-")
    assert diagnostics["backfill_excluded_platforms"] == 0
