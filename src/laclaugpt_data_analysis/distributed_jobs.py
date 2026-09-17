"""Redis-backed job coordination for distributed AI26 runs.

MongoDB is the durable source of truth for jobs/results; Redis supplies only
transient claim/lease/heartbeat state. Guarantees implemented here:

- **Atomic claim**: a worker claims a pending job with a Redis ``SET NX``
  lease key; two workers can never both hold the lease for one job.
- **Lease expiry/reclaim**: leases carry a TTL. A crashed worker's lease
  expires and any worker may reclaim the job safely (durable state is only
  advanced by result writes, never by claiming).
- **Idempotent results**: durable result writes are keyed by
  ``idempotency_key``; two writes with the same key are one logical result.
  The durable write happens *before* the queue acknowledgement.
- **Safe retries**: attempts increment durably; a failed job returns to
  ``pending`` after the lease is released.

Redis documents never contain secrets or private config payloads.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

logger = logging.getLogger(__name__)

CLAIM_KEY_PREFIX = "laclaugpt:{project}:claim:{job_id}"
STREAM_KEY = "laclaugpt:{project}:stream:analysis-requested"
DONE_STREAM_KEY = "laclaugpt:{project}:stream:analyzed"
DEFAULT_LEASE_SECONDS = 600
DEFAULT_MAX_ATTEMPTS = 5


def idempotency_key(
    run_id: str, source_url: str, arena: str, analysis_version: str
) -> str:
    """Deterministic identity of one logical analysis result."""
    payload = "\x1f".join((run_id, source_url, arena, analysis_version))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RedisLike(Protocol):
    """Minimal Redis surface (decode_responses=True clients satisfy this)."""

    def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> Any: ...

    def get(self, name: str) -> Any: ...

    def delete(self, *names: str) -> Any: ...

    def xadd(self, name: str, fields: dict[str, str], maxlen: int | None = None, approximate: bool = True) -> Any: ...

    def expire(self, name: str, seconds: int) -> Any: ...


class MongoCollectionLike(Protocol):
    """Minimal pymongo collection surface used by the coordinator."""

    def find_one(self, filter: dict[str, Any], projection: dict[str, Any] | None = None) -> dict[str, Any] | None: ...

    def update_one(self, filter: dict[str, Any], update: dict[str, Any], upsert: bool = False) -> Any: ...

    def replace_one(self, filter: dict[str, Any], replacement: dict[str, Any], upsert: bool = False) -> Any: ...

    def count_documents(self, filter: dict[str, Any]) -> int: ...


@dataclass
class JobDocument:
    """Durable job state; mirrors schemas/distributed-run.schema.json $defs.job_document."""

    run_id: str
    project_id: str
    job_id: str
    idempotency_key: str
    source_url: str
    arena: str
    state: str = "pending"
    attempts: int = 0
    claimed_by: str | None = None
    claim_expires_at: str | None = None
    result_ref: str | None = None
    analysis_version: str = "1.0"

    def to_doc(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "project_id": self.project_id,
            "job_id": self.job_id,
            "idempotency_key": self.idempotency_key,
            "source_url": self.source_url,
            "arena": self.arena,
            "state": self.state,
            "attempts": self.attempts,
            "claimed_by": self.claimed_by,
            "claim_expires_at": self.claim_expires_at,
            "result_ref": self.result_ref,
            "analysis_version": self.analysis_version,
        }

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> JobDocument:
        return cls(
            run_id=str(doc["run_id"]),
            project_id=str(doc["project_id"]),
            job_id=str(doc["job_id"]),
            idempotency_key=str(doc["idempotency_key"]),
            source_url=str(doc["source_url"]),
            arena=str(doc["arena"]),
            state=str(doc.get("state", "pending")),
            attempts=int(doc.get("attempts", 0)),
            claimed_by=doc.get("claimed_by"),
            claim_expires_at=doc.get("claim_expires_at"),
            result_ref=doc.get("result_ref"),
            analysis_version=str(doc.get("analysis_version", "1.0")),
        )


@dataclass
class ClaimOutcome:
    job: JobDocument
    claimed: bool
    reason: str = ""
    lease_seconds: int = DEFAULT_LEASE_SECONDS
    manifest: dict[str, Any] = field(default_factory=dict)


class DistributedJobCoordinator:
    """Coordinate concurrent analysis workers over Redis leases + Mongo state."""

    def __init__(
        self,
        redis: RedisLike,
        jobs: MongoCollectionLike,
        results: MongoCollectionLike,
        *,
        project_id: str,
        run_id: str,
        worker_id: str,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        self._redis = redis
        self._jobs = jobs
        self._results = results
        self.project_id = project_id
        self.run_id = run_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.manifest = dict(manifest or {})

    # -- claiming -----------------------------------------------------------

    def _claim_key(self, job_id: str) -> str:
        return CLAIM_KEY_PREFIX.format(project=self.project_id, job_id=job_id)

    def claim_next(self, *, arenas: tuple[str, ...] | None = None) -> ClaimOutcome | None:
        """Atomically claim the oldest pending, unleased job; None if none available.

        Expired leases are reclaimed transparently. Durable job state moves to
        ``claimed`` only after the Redis lease is won.
        """
        query: dict[str, Any] = {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "state": {"$in": ["pending", "claimed"]},
        }
        if arenas:
            query["arena"] = {"$in": list(arenas)}
        visited: set[str] = set()
        cursor_doc = self._jobs.find_one(query)
        while cursor_doc is not None:
            if cursor_doc.get("job_id") in visited:
                # All candidates seen: unleased-but-held or done; stop polling.
                return None
            visited.add(str(cursor_doc.get("job_id")))
            outcome = self._try_claim(JobDocument.from_doc(cursor_doc))
            if outcome is not None:
                return outcome
            cursor_doc = self._jobs.find_one(query)
        return None

    def _try_claim(self, job: JobDocument) -> ClaimOutcome | None:
        if job.state == "done":
            return None
        if job.state == "failed" or job.attempts >= self.max_attempts:
            return None
        if job.state == "claimed" and not self._lease_expired(job):
            return None
        if self._already_done(job):
            self._jobs.update_one(
                {"job_id": job.job_id, "run_id": self.run_id},
                {"$set": {"state": "done", "result_ref": self._existing_result_ref(job)}},
            )
            return None

        won = self._redis.set(
            self._claim_key(job.job_id),
            self.worker_id,
            nx=True,
            ex=self.lease_seconds,
        )
        if not won:
            return None
        expires = (datetime.now(UTC) + timedelta(seconds=self.lease_seconds)).isoformat()
        updated = dict(job.to_doc())
        updated.update(
            state="claimed", claimed_by=self.worker_id, claim_expires_at=expires
        )
        self._jobs.replace_one({"job_id": job.job_id, "run_id": self.run_id}, updated, upsert=True)
        return ClaimOutcome(
            job=JobDocument.from_doc(updated),
            claimed=True,
            reason="lease acquired",
            lease_seconds=self.lease_seconds,
            manifest=self.manifest,
        )

    def _lease_expired(self, job: JobDocument) -> bool:
        if not job.claim_expires_at:
            return True
        try:
            expiry = datetime.fromisoformat(str(job.claim_expires_at))
        except ValueError:
            return True
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return expiry <= datetime.now(UTC)

    def _already_done(self, job: JobDocument) -> bool:
        return (
            self._results.find_one({"idempotency_key": job.idempotency_key}, {"_id": 1})
            is not None
        )

    def _existing_result_ref(self, job: JobDocument) -> str:
        result = self._results.find_one(
            {"idempotency_key": job.idempotency_key},
            {"_id": 1, "job_id": 1},
        )
        if result and result.get("_id") is not None:
            return f"mongodb:{self.project_id}__results/{result['_id']}"
        return f"mongodb:{self.project_id}__results/{job.idempotency_key}"

    # -- completing ---------------------------------------------------------

    def complete(self, job: JobDocument, result: dict[str, Any]) -> bool:
        """Write the durable result then acknowledge; returns False on duplicates.

        Order matters: MongoDB result first, queue ack second. If the worker
        dies between the two, the retry sees the idempotency key already
        present and skips reprocessing.
        """
        result_doc = dict(result)
        result_doc.setdefault("idempotency_key", job.idempotency_key)
        result_doc.setdefault("run_id", self.run_id)
        result_doc.setdefault("project_id", self.project_id)
        result_doc.setdefault("arena", job.arena)
        result_doc.setdefault("source_url", job.source_url)
        result_doc.setdefault("worker_id", self.worker_id)
        result_doc.setdefault("completed_at", datetime.now(UTC).isoformat())

        existing = self._results.find_one(
            {"idempotency_key": job.idempotency_key}, {"_id": 1}
        )
        if existing is not None:
            logger.info("idempotent skip: result for key already durable")
            self._finish(job, state="done")
            return False
        self._results.replace_one(
            {"idempotency_key": job.idempotency_key}, result_doc, upsert=True
        )
        self._finish(job, state="done")
        self._ack(job)
        return True

    def fail(self, job: JobDocument, error: str) -> None:
        """Record a failure and return the job to pending for safe retry."""
        attempts = job.attempts + 1
        state = "failed" if attempts >= self.max_attempts else "pending"
        self._jobs.update_one(
            {"job_id": job.job_id, "run_id": self.run_id},
            {
                "$set": {
                    "state": state,
                    "attempts": attempts,
                    "claimed_by": None,
                    "claim_expires_at": None,
                }
            },
        )
        self._redis.delete(self._claim_key(job.job_id))
        self._redis.xadd(
            DONE_STREAM_KEY.format(project=self.project_id),
            {
                "job_id": job.job_id,
                "state": state,
                "worker_id": self.worker_id,
                "error": error[:500],
            },
            maxlen=10000,
        )

    def heartbeat(self, job: JobDocument) -> None:
        """Extend the lease while a long job is still running."""
        self._redis.expire(self._claim_key(job.job_id), self.lease_seconds)

    def release(self, job: JobDocument) -> None:
        """Give up a claim without recording failure (e.g. graceful shutdown)."""
        self._jobs.update_one(
            {"job_id": job.job_id, "run_id": self.run_id},
            {"$set": {"state": "pending", "claimed_by": None, "claim_expires_at": None}},
        )
        self._redis.delete(self._claim_key(job.job_id))

    def _finish(self, job: JobDocument, *, state: str) -> None:
        self._jobs.update_one(
            {"job_id": job.job_id, "run_id": self.run_id},
            {
                "$set": {
                    "state": state,
                    "claimed_by": self.worker_id,
                    "claim_expires_at": None,
                }
            },
        )
        self._redis.delete(self._claim_key(job.job_id))

    def _ack(self, job: JobDocument) -> None:
        self._redis.xadd(
            DONE_STREAM_KEY.format(project=self.project_id),
            {
                "job_id": job.job_id,
                "state": "done",
                "worker_id": self.worker_id,
                "idempotency_key": job.idempotency_key,
            },
            maxlen=10000,
        )

    # -- run status ---------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Researcher-safe run summary: counts per state/arena, no payloads."""
        out: dict[str, Any] = {"run_id": self.run_id, "project_id": self.project_id}
        per_state: dict[str, int] = {}
        for state in ("pending", "claimed", "done", "failed"):
            per_state[state] = self._jobs.count_documents(
                {"run_id": self.run_id, "project_id": self.project_id, "state": state}
            )
        out["states"] = per_state
        per_arena: dict[str, int] = {}
        for arena in ("elites", "grassroots", "parliamentary"):
            per_arena[arena] = self._jobs.count_documents(
                {"run_id": self.run_id, "project_id": self.project_id, "arena": arena}
            )
        out["arenas"] = per_arena
        out["manifest_hash_keys"] = sorted(self.manifest.get("config_hashes", {}).keys())
        return out


def enqueue_jobs(
    jobs: MongoCollectionLike,
    *,
    run_id: str,
    project_id: str,
    records: list[dict[str, Any]],
    analysis_version: str = "1.0",
) -> int:
    """Create durable pending jobs from canonical records (bounded test sample).

    Each record must carry a non-empty canonical ``source_url`` and an ``arena``.
    """
    created = 0
    for record in records:
        source_url = str(record.get("source_url", "")).strip()
        arena = str(record.get("arena", "")).strip()
        if not source_url or arena not in {"elites", "grassroots", "parliamentary"}:
            raise ValueError("records require canonical source_url and a known arena")
        key = idempotency_key(run_id, source_url, arena, analysis_version)
        existing = jobs.find_one({"idempotency_key": key}, {"_id": 1})
        if existing is not None:
            continue
        doc = JobDocument(
            run_id=run_id,
            project_id=project_id,
            job_id=key[:24] + "-" + hashlib.sha1(source_url.encode()).hexdigest()[:8],
            idempotency_key=key,
            source_url=source_url,
            arena=arena,
            analysis_version=analysis_version,
        ).to_doc()
        jobs.replace_one({"idempotency_key": key}, doc, upsert=True)
        created += 1
    return created


def dumps_safe(payload: dict[str, Any]) -> str:
    """JSON for Redis documents; refuses obvious secret-looking keys."""
    forbidden = ("password", "secret", "token", "api_key", "access_key")
    for key in payload:
        if any(marker in key.lower() for marker in forbidden):
            raise ValueError(f"refusing to publish secret-looking key {key!r} to Redis")
    return json.dumps(payload, ensure_ascii=False, default=str)