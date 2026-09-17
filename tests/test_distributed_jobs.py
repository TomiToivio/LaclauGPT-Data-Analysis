"""Distributed job-claim/idempotency/lease tests (issue #15, Analysis)."""
from __future__ import annotations

import time
from typing import Any

import pytest

from laclaugpt_data_analysis.distributed_env import TEST_MODEL
from laclaugpt_data_analysis.distributed_jobs import (
    DistributedJobCoordinator,
    JobDocument,
    dumps_safe,
    enqueue_jobs,
    idempotency_key,
)
from tests.fakes_distributed import FakeCollection, FakeRedis

RUN_ID = "ai26-dist-test-001"
PROJECT = "ai26"


def make_job(source_url: str = "https://example.invalid/post/1", arena: str = "elites") -> dict[str, Any]:
    key = idempotency_key(RUN_ID, source_url, arena, "1.0")
    return JobDocument(
        run_id=RUN_ID,
        project_id=PROJECT,
        job_id=key[:24] + "-abcdef01",
        idempotency_key=key,
        source_url=source_url,
        arena=arena,
    ).to_doc()


def coordinator(
    redis: FakeRedis | None = None,
    jobs: FakeCollection | None = None,
    results: FakeCollection | None = None,
    worker_id: str = "worker-a",
    lease_seconds: int = 600,
    max_attempts: int = 5,
) -> DistributedJobCoordinator:
    return DistributedJobCoordinator(
        redis or FakeRedis(),
        jobs or FakeCollection(),
        results or FakeCollection(),
        project_id=PROJECT,
        run_id=RUN_ID,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        max_attempts=max_attempts,
        manifest={"config_hashes": {"codebook": "x", "analysis_settings": "y"}},
    )


def test_idempotency_key_deterministic() -> None:
    one = idempotency_key(RUN_ID, "https://example.invalid/a", "elites", "1.0")
    two = idempotency_key(RUN_ID, "https://example.invalid/a", "elites", "1.0")
    other = idempotency_key(RUN_ID, "https://example.invalid/a", "grassroots", "1.0")
    assert one == two
    assert one != other


def test_two_workers_cannot_claim_same_job() -> None:
    jobs = FakeCollection([make_job()])
    redis = FakeRedis()
    first = coordinator(redis=redis, jobs=jobs, worker_id="worker-a")
    second = coordinator(redis=redis, jobs=jobs, worker_id="worker-b")

    outcome_a = first.claim_next()
    assert outcome_a is not None and outcome_a.claimed
    assert outcome_a.job.claimed_by == "worker-a"

    outcome_b = second.claim_next()
    assert outcome_b is None  # lease held by worker-a, lease not expired


def test_claim_is_exclusive_across_many_workers() -> None:
    jobs = FakeCollection([make_job()])
    redis = FakeRedis()
    workers = [
        coordinator(redis=redis, jobs=jobs, worker_id=f"w-{index}")
        for index in range(8)
    ]
    claims = [worker.claim_next() for worker in workers]
    claimed = [outcome for outcome in claims if outcome and outcome.claimed]
    assert len(claimed) == 1


def test_lease_expiry_allows_reclaim() -> None:
    jobs = FakeCollection([make_job()])
    redis = FakeRedis()
    first = coordinator(redis=redis, jobs=jobs, worker_id="worker-a", lease_seconds=1)
    outcome = first.claim_next()
    assert outcome is not None and outcome.claimed

    time.sleep(1.1)  # let the fake lease expire
    second = coordinator(redis=redis, jobs=jobs, worker_id="worker-b")
    reclaimed = second.claim_next()
    assert reclaimed is not None and reclaimed.claimed
    assert reclaimed.job.claimed_by == "worker-b"


def test_completed_job_not_reprocessed_by_reclaim() -> None:
    doc = make_job()
    jobs = FakeCollection([doc])
    results = FakeCollection()
    redis = FakeRedis()
    first = coordinator(redis=redis, jobs=jobs, results=results, worker_id="worker-a", lease_seconds=1)
    outcome = first.claim_next()
    assert outcome is not None
    first.complete(outcome.job, {"analysis": {"summary": "provisional result"}})

    time.sleep(1.1)
    second = coordinator(redis=redis, jobs=jobs, results=results, worker_id="worker-b")
    assert second.claim_next() is None  # durable result exists -> not re-claimed


def test_duplicate_complete_is_idempotent() -> None:
    jobs = FakeCollection([make_job()])
    results = FakeCollection()
    worker = coordinator(jobs=jobs, results=results, worker_id="worker-a")
    outcome = worker.claim_next()
    assert outcome is not None

    first = worker.complete(outcome.job, {"analysis": {"summary": "result"}})
    second = worker.complete(outcome.job, {"analysis": {"summary": "result"}})
    assert first is True
    assert second is False  # duplicate skipped, no second durable write
    assert results.count_documents({}) == 1


def test_fail_returns_job_to_pending_then_marks_failed() -> None:
    jobs = FakeCollection([make_job()])
    redis = FakeRedis()
    worker = coordinator(redis=redis, jobs=jobs, worker_id="worker-a", max_attempts=2)

    outcome = worker.claim_next()
    assert outcome is not None
    worker.fail(outcome.job, "model error")
    doc = jobs.find_one({"job_id": outcome.job.job_id})
    assert doc is not None and doc["state"] == "pending"
    assert doc["attempts"] == 1
    assert redis.get(f"laclaugpt:{PROJECT}:claim:{outcome.job.job_id}") is None

    outcome2 = worker.claim_next()
    assert outcome2 is not None
    worker.fail(outcome2.job, "model error again")
    doc = jobs.find_one({"job_id": outcome.job.job_id})
    assert doc is not None and doc["state"] == "failed"
    assert worker.claim_next() is None


def test_release_gives_claim_back() -> None:
    jobs = FakeCollection([make_job()])
    redis = FakeRedis()
    worker = coordinator(redis=redis, jobs=jobs, worker_id="worker-a")
    outcome = worker.claim_next()
    assert outcome is not None
    worker.release(outcome.job)
    other = coordinator(redis=redis, jobs=jobs, worker_id="worker-b")
    reborrowed = other.claim_next()
    assert reborrowed is not None and reborrowed.claimed


def test_enqueue_is_idempotent_and_validates_records() -> None:
    jobs = FakeCollection()
    records = [
        {"source_url": "https://example.invalid/a", "arena": "elites"},
        {"source_url": "https://example.invalid/b", "arena": "grassroots"},
        {"source_url": "https://example.invalid/a", "arena": "elites"},  # duplicate
    ]
    created = enqueue_jobs(jobs, run_id=RUN_ID, project_id=PROJECT, records=records)
    assert created == 2
    again = enqueue_jobs(jobs, run_id=RUN_ID, project_id=PROJECT, records=records)
    assert again == 0

    with pytest.raises(ValueError, match="source_url"):
        enqueue_jobs(
            jobs,
            run_id=RUN_ID,
            project_id=PROJECT,
            records=[{"source_url": "", "arena": "elites"}],
        )
    with pytest.raises(ValueError, match="arena"):
        enqueue_jobs(
            jobs,
            run_id=RUN_ID,
            project_id=PROJECT,
            records=[{"source_url": "https://example.invalid/c", "arena": "conspiracy"}],
        )


def test_arenas_do_not_overwrite_one_another() -> None:
    jobs = FakeCollection(
        [
            make_job("https://example.invalid/a", arena="elites"),
            make_job("https://example.invalid/b", arena="grassroots"),
        ]
    )
    worker = coordinator(jobs=jobs, worker_id="worker-a")
    first = worker.claim_next(arenas=("elites",))
    assert first is not None and first.job.arena == "elites"
    worker.complete(first.job, {"analysis": {}})
    second = worker.claim_next(arenas=("elites",))
    assert second is None  # elites is done
    third = worker.claim_next(arenas=("grassroots",))
    assert third is not None and third.job.arena == "grassroots"


def test_status_is_payload_free() -> None:
    jobs = FakeCollection(
        [
            make_job("https://example.invalid/a", arena="elites"),
            make_job("https://example.invalid/b", arena="grassroots"),
        ]
    )
    worker = coordinator(jobs=jobs, worker_id="worker-a")
    outcome = worker.claim_next()
    assert outcome is not None
    worker.complete(outcome.job, {"analysis": {"summary": "x"}})
    status = worker.status()
    assert status["states"]["done"] == 1
    assert status["states"]["pending"] == 1
    assert status["arenas"]["elites"] == 1
    assert status["arenas"]["grassroots"] == 1
    # No record payloads or result documents leak into the run summary.
    assert "summary" not in str(status)
    assert "https://example.invalid" not in str(status)


def test_dumps_safe_refuses_secret_keys() -> None:
    with pytest.raises(ValueError, match="secret"):
        dumps_safe({"s3_secret": "value"})
    dumps_safe({"job_id": "x", "state": "pending"})


def test_worker_survives_model_failure_and_retries_idempotently() -> None:
    """Simulate a worker crash after claim: lease expiry + retry reaches done once."""
    jobs = FakeCollection([make_job()])
    results = FakeCollection()
    redis = FakeRedis()

    # Worker A claims, then "crashes" without completing.
    crashed = coordinator(
        redis=redis, jobs=jobs, results=results, worker_id="crashed-a", lease_seconds=1
    )
    outcome = crashed.claim_next()
    assert outcome is not None
    crashed._redis.expire = lambda *a, **k: None  # no heartbeat, crash freezes lease

    time.sleep(1.1)
    # Worker B reclaims and completes.
    healthy = coordinator(
        redis=redis, jobs=jobs, results=results, worker_id="healthy-b", lease_seconds=600
    )
    reclaimed = healthy.claim_next()
    assert reclaimed is not None and reclaimed.claimed
    assert healthy.complete(reclaimed.job, {"analysis": {"summary": "ok"}}) is True

    # No worker can redo the work.
    assert healthy.claim_next() is None
    assert results.count_documents({}) == 1


def test_max_attempts_prevents_infinite_retry() -> None:
    jobs = FakeCollection([make_job()])
    redis = FakeRedis()
    worker = coordinator(redis=redis, jobs=jobs, worker_id="w", max_attempts=2)
    for _ in range(2):
        outcome = worker.claim_next()
        assert outcome is not None
        worker.fail(outcome.job, "boom")
    assert worker.claim_next() is None


def test_local_model_policy_constant() -> None:
    assert TEST_MODEL == "gemma4:12b"