"""An idle cycle must not stand in for a drained corpus (issue #382, upstream #302).

EP24 #302 fixed a class of false-complete reporting: a stage that had finished every
eligible row logged the same "no eligible rows" warning as a stage whose input was
empty or misconfigured, so the log could not tell "nothing left to do" from "nothing
came in".

AI26 has the same shape at the seed step. ``seed_ready_tasks`` returned a bare count,
so these four situations were one number, ``0``:

* the work budget was zero;
* Collection handed over nothing for this run;
* every ready handoff was already analysed at this generation;
* every ready handoff was a terminal failure.

Only one of them is benign. These tests pin the distinction, and pin that the
published count -- the contract eleven existing call sites depend on -- is unchanged.
"""
from __future__ import annotations

from types import SimpleNamespace

from laclaugpt_data_analysis.distributed_worker import (
    SEED_ALL_REJECTED,
    SEED_BUDGET_ZERO,
    SEED_NO_NEW_WORK,
    SEED_SEEDED,
    SEED_UPSTREAM_EMPTY,
    seed_disposition,
    seed_ready_tasks,
)


class FakeBinding:
    manifest = SimpleNamespace(run_id="ai26-run")

    @staticmethod
    def task_from_handoff(handoff):
        return SimpleNamespace(idempotency_key=handoff["handoff_key"])


class FakeHandoff:
    """A handoff that knows nothing about run ids, like an empty Collection result."""

    def __init__(self, count: int):
        self.rows = [
            {"status": "ready", "run_id": "ai26-run", "handoff_key": f"handoff-{index}"}
            for index in range(count)
        ]
        self.queries: list[str] = []

    def ready_handoffs(self, run_id: str, *, limit: int, offset: int = 0):
        self.queries.append(run_id)
        return self.rows[offset : offset + limit]


class FakeQueue:
    def __init__(self):
        self.published = []

    def publish(self, task):
        self.published.append(task)


class FakeDurableStore:
    def __init__(self):
        self.completed: set[str] = set()
        self.terminal: set[str] = set()

    def has_result(self, idempotency_key: str, fingerprint: str = "") -> bool:
        return idempotency_key in self.completed

    def has_terminal_failure(self, idempotency_key: str) -> bool:
        return idempotency_key in self.terminal

    def rearm_terminal_failure(self, idempotency_key: str) -> int:
        self.terminal.discard(idempotency_key)
        return 1


def _seed(*, rows: int, limit: int = 5, durable: FakeDurableStore | None = None):
    diagnostics: dict[str, int] = {}
    queue = FakeQueue()
    seeded = seed_ready_tasks(
        FakeBinding(),
        FakeHandoff(rows),
        queue,
        durable or FakeDurableStore(),
        limit=limit,
        diagnostics=diagnostics,
    )
    return seeded, queue, diagnostics


def test_upstream_empty_is_not_a_complete_corpus() -> None:
    """Zero handoffs means Collection handed over nothing, not that work is done."""
    seeded, queue, diagnostics = _seed(rows=0)

    assert seeded == 0
    assert queue.published == []
    assert diagnostics["examined"] == 0
    assert diagnostics["published"] == 0
    assert seed_disposition(diagnostics) == SEED_UPSTREAM_EMPTY


def test_a_complete_corpus_is_reported_as_no_new_work() -> None:
    """Every row already analysed is the benign zero, and must say so."""
    durable = FakeDurableStore()
    durable.completed.update({"handoff-0", "handoff-1", "handoff-2"})

    seeded, _, diagnostics = _seed(rows=3, durable=durable)

    assert seeded == 0
    assert diagnostics["examined"] == 3
    assert diagnostics["already_analyzed"] == 3
    assert diagnostics["published"] == 0
    assert seed_disposition(diagnostics) == SEED_NO_NEW_WORK


def test_terminal_failures_alone_are_no_new_work_not_upstream_empty() -> None:
    """Permanent failures are an actionable zero, and distinct from an empty source."""
    durable = FakeDurableStore()
    durable.terminal.update({"handoff-0", "handoff-1"})

    seeded, _, diagnostics = _seed(rows=2, durable=durable)

    assert seeded == 0
    assert diagnostics["examined"] == 2
    assert diagnostics["terminal_failure"] == 2
    assert diagnostics["already_analyzed"] == 0
    assert seed_disposition(diagnostics) == SEED_NO_NEW_WORK


def test_a_zero_budget_is_named_rather_than_reported_as_an_empty_source() -> None:
    """`--max-tasks 0` asks for no work; it is not evidence about the source."""
    seeded, _, diagnostics = _seed(rows=4, limit=0)

    assert seeded == 0
    assert diagnostics["limit"] == 0
    assert diagnostics["examined"] == 0
    assert seed_disposition(diagnostics) == SEED_BUDGET_ZERO


def test_the_published_count_contract_is_unchanged() -> None:
    """Eleven call sites compare the return to an int; diagnostics must not alter it."""
    durable = FakeDurableStore()
    durable.completed.add("handoff-0")

    seeded, queue, diagnostics = _seed(rows=4, limit=3, durable=durable)

    assert seeded == 3 == len(queue.published)
    assert diagnostics["examined"] == 4
    assert diagnostics["already_analyzed"] == 1
    assert diagnostics["published"] == 3
    assert seed_disposition(diagnostics) == SEED_SEEDED


def test_a_page_of_malformed_handoffs_is_not_no_new_work() -> None:
    """The quarantine's own zero must not be reported as a drained corpus.

    Rows arrived here; every one was refused. ``no_new_work`` would turn an identity
    regression into a quiet queue, which is the failure this whole issue is about.
    """
    class MalformedHandoff(FakeHandoff):
        @staticmethod
        def ready_handoffs(run_id: str, *, limit: int, offset: int = 0):
            return [{"handoff_key": "", "run_id": "x"}] * 2

    class StrictBinding(FakeBinding):
        @staticmethod
        def task_from_handoff(handoff):
            raise KeyError("missing source_url")

    diagnostics: dict[str, int] = {}
    rejected: list[dict[str, str]] = []
    seeded = seed_ready_tasks(
        StrictBinding(),
        MalformedHandoff(0),
        FakeQueue(),
        FakeDurableStore(),
        limit=5,
        rejected=rejected,
        diagnostics=diagnostics,
    )

    assert seeded == 0
    assert len(rejected) == 2
    assert diagnostics["examined"] == 2
    assert diagnostics["rejected"] == 2
    assert seed_disposition(diagnostics) == SEED_ALL_REJECTED


def test_diagnostics_are_optional_and_do_not_change_behaviour() -> None:
    """Callers that pass nothing keep the old signature and the old answer."""
    queue = FakeQueue()
    seeded = seed_ready_tasks(
        FakeBinding(), FakeHandoff(2), queue, FakeDurableStore(), limit=2
    )

    assert seeded == 2 == len(queue.published)


def test_diagnostics_are_overwritten_not_accumulated() -> None:
    """A reused mapping reports one cycle's counts, never a running total."""
    diagnostics = {"examined": 999, "published": 999}
    seed_ready_tasks(
        FakeBinding(),
        FakeHandoff(1),
        FakeQueue(),
        FakeDurableStore(),
        limit=1,
        diagnostics=diagnostics,
    )

    assert diagnostics["examined"] == 1
    assert diagnostics["published"] == 1
    assert seed_disposition(diagnostics) == SEED_SEEDED
