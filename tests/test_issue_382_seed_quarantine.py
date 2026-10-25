"""Issue #382: one malformed handoff must not stop the whole seed.

The failure this pins
---------------------

`seed_ready_tasks` converts each ready Collection handoff into a task. The conversion validates
the identity — a handoff with no `source_url`, no `handoff_key`, or a `run_id` that does not match
the frozen manifest raises. Before this change the exception left the seeding pass entirely, so:

* every record *after* the bad one in the same batch was never queued;
* the bad row is still `ready` in the collection, so the next cron tick read it again and failed
  again — the pipeline stalled permanently, and the tick looked like an idle cycle.

That is the class the upstream Multimodal-Analysis fixes #299, #303 and #304 describe: a single
unidentifiable row taking down a country batch, identity needing recovery where it is provable,
and rows that cannot be identified needing quarantine-with-audit rather than a crash or a drop.

What is asserted here is the **behaviour of the seeding pass**: what it publishes, what it
reports, and that it terminates. It is not a test of the case's prose or of any EP24 code.
"""
from __future__ import annotations

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.distributed_worker import seed_ready_tasks
from laclaugpt_data_analysis.task_queue import (
    InMemoryTaskQueue,
    InMemoryTaskStore,
    TaskEnvelope,
)

RUN = "test-run"


class Binding:
    """A binding whose conversion validates exactly as the production one does."""

    manifest = type("Manifest", (), {"run_id": RUN})()

    @staticmethod
    def task_from_handoff(handoff: dict) -> TaskEnvelope:
        if str(handoff.get("run_id") or "") != RUN:
            raise ValueError("Collection handoff run does not match frozen run manifest")
        task = TaskEnvelope(
            task_id=f"analysis:{handoff.get('handoff_key') or ''}",
            idempotency_key=str(handoff.get("handoff_key") or ""),
            project_id="ai26",
            run_id=str(handoff.get("run_id") or ""),
            task_type="analyze-record",
            record_ref=str(handoff.get("source_url") or ""),
            schema_version=SCHEMA_VERSION,
            config_revision="test-config",
            codebook_revision="test-codebook",
        )
        task.validate()  # raises ValueError naming the missing field
        return task


class Handoff:
    """Ready handoffs, in the order given, paginated the way the Mongo adapter is."""

    def __init__(self, *rows: dict):
        self.rows = list(rows)

    def ready_handoffs(self, _run_id, *, limit, offset=0):
        return self.rows[offset:offset + limit]


def row(key: str, *, url: str | None = None, run: str = RUN) -> dict:
    return {
        "status": "ready",
        "run_id": run,
        "handoff_key": key,
        "source_url": f"https://example.invalid/{key}" if url is None else url,
    }


def seed(handoff: Handoff, *, limit: int = 100, page_size: int | None = None):
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    rejected: list[dict[str, str]] = []
    published = seed_ready_tasks(
        Binding(), handoff, queue, store, limit=limit, page_size=page_size, rejected=rejected
    )
    return published, queue, rejected


def test_one_unidentifiable_handoff_does_not_stop_the_batch() -> None:
    """The whole point: a bad row in the middle leaves every healthy row queued."""
    published, queue, rejected = seed(
        Handoff(row("good-1"), row("bad", url=""), row("good-2"))
    )
    assert published == 2, "the healthy records around the bad one must still be seeded"
    assert len(queue.pending) == 2
    assert [claimed.task.idempotency_key for claimed in queue.pending] == ["good-1", "good-2"]
    assert len(rejected) == 1


def test_a_bad_handoff_first_does_not_hide_the_rest() -> None:
    """A bad row at the head of the page used to hide every later row in that page."""
    published, queue, rejected = seed(Handoff(row("bad", url=""), row("good")))
    assert published == 1
    assert [claimed.task.idempotency_key for claimed in queue.pending] == ["good"]
    assert rejected[0]["handoff_key"] == "bad"


def test_a_bad_row_does_not_stop_a_later_page() -> None:
    """Pagination must keep advancing past a rejected page."""
    rows = [row("bad", url=""), row("good-1"), row("good-2")]
    published, queue, rejected = seed(Handoff(*rows), limit=10, page_size=2)
    assert published == 2, "page one had one bad row; page two must still be read"
    assert len(rejected) == 1


def test_an_all_invalid_batch_reports_and_returns_zero() -> None:
    """An all-invalid page is a reported condition, not an exception and not a success."""
    published, queue, rejected = seed(
        Handoff(row("a", url=""), row("b", url=""), row("c", url=""))
    )
    assert published == 0
    assert queue.pending == []
    assert len(rejected) == 3, "nothing may be dropped silently"


def test_the_rejection_names_the_field_and_the_reason() -> None:
    _, _, rejected = seed(Handoff(row("bad", url="")))
    assert rejected[0]["handoff_key"] == "bad"
    assert rejected[0]["run_id"] == RUN
    assert "record_ref" in rejected[0]["reason"], rejected[0]["reason"]
    assert rejected[0]["reason"].startswith("ValueError:")


def test_a_wrong_run_handoff_is_quarantined_the_same_way() -> None:
    """Identity mismatch is the same failure class as a missing identity."""
    published, _, rejected = seed(Handoff(row("other-run", run="some-other-run"), row("good")))
    assert published == 1
    assert len(rejected) == 1
    assert "run" in rejected[0]["reason"].lower() or "manifest" in rejected[0]["reason"].lower()


def test_a_clean_batch_reports_nothing_and_seeds_everything() -> None:
    """The happy path is unchanged: same return value, no rejections."""
    published, queue, rejected = seed(Handoff(row("one"), row("two"), row("three")))
    assert published == 3
    assert len(queue.pending) == 3
    assert rejected == []


def test_the_limit_still_bounds_published_tasks() -> None:
    """A limit counts work published, and a rejection does not consume it."""
    published, _, rejected = seed(Handoff(row("bad", url=""), row("one"), row("two")), limit=2)
    assert published == 2, "the limit bounds published work, not rows examined"
    assert len(rejected) == 1, "the bad row is still reported"


def test_the_return_value_keeps_its_meaning(caplog) -> None:
    """The contract six existing call sites assert: the return value is tasks published."""
    import logging

    with caplog.at_level(logging.WARNING, logger="laclaugpt_data_analysis.distributed_worker"):
        published, _, _ = seed(Handoff(row("bad", url=""), row("good")))
    assert published == 1
    assert any("quarantined at seed" in record.getMessage() for record in caplog.records), (
        "the rejection must be logged"
    )


def test_ten_thousand_bad_rows_log_once_not_ten_thousand_times(caplog) -> None:
    """A systemic identity regression must be loud once, not fill the log."""
    import logging

    from laclaugpt_data_analysis import distributed_worker as worker

    rows = [row(f"bad-{index}", url="") for index in range(worker._REJECTION_DETAIL_LIMIT + 5)]
    with caplog.at_level(logging.WARNING, logger="laclaugpt_data_analysis.distributed_worker"):
        published, _, rejected = seed(Handoff(*rows))
    assert published == 0
    assert len(rejected) == len(rows), "every rejection is still reported to the caller"
    named = [r for r in caplog.records if "quarantined at seed" in r.getMessage()]
    assert len(named) == worker._REJECTION_DETAIL_LIMIT
    summarised = [r for r in caplog.records if "could not become tasks" in r.getMessage()]
    assert len(summarised) == 1
