"""Task-queue contracts: envelopes, resume identity and store protocols.

The queue is split by responsibility, so a reader can open the one file that
answers their question:

* ``models.py`` (this file) -- what a task *is*, and what a queue or store must do;
* ``memory.py`` -- in-process adapters used by tests and single-process runs;
* ``sqlite_store.py`` -- durable local result history without any server;
* ``mongo_store.py`` -- durable distributed result history;
* ``redis_queue.py`` -- Redis Streams transport with consumer groups;
* ``worker.py`` -- the claim/analyse/acknowledge loop and its settings wiring.

The protocols here are the only contract the worker depends on, so adapters can
be swapped without touching the scientific pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol

FAILURE_RESPONSE_RAW_MAX_CHARS = 16_384


def bounded_failure_diagnostics(
    diagnostics: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Normalize and bound model-output diagnostics before durable persistence."""
    if not diagnostics:
        return {}
    raw = str(diagnostics.get("response_raw") or "")
    finish_reason = str(diagnostics.get("finish_reason") or "")
    outcome = str(diagnostics.get("terminal_reason") or "")
    # An infrastructure failure is a fact about the provider, not about the model's output, and it is a
    # single boolean: it survives bounding so an operator can tell "the endpoint was down" from "the
    # document was unanalysable" without reading the error string (#414).
    infrastructure = diagnostics.get("infrastructure") is True
    if not raw and not finish_reason and not outcome:
        return {"infrastructure": True} if infrastructure else {}
    result = {
        "response_raw": raw[:FAILURE_RESPONSE_RAW_MAX_CHARS],
        "response_raw_chars": len(raw),
        "response_raw_truncated": len(raw) > FAILURE_RESPONSE_RAW_MAX_CHARS,
        "finish_reason": finish_reason,
        "diagnostic_only": True,
    }
    if infrastructure:
        result["infrastructure"] = True
    if outcome == "unanalysable_within_budget":
        result["terminal_reason"] = outcome
        for key in (
            "output_budget_tokens",
            "required_output_tokens_lower_bound",
            "generated_output_chars",
        ):
            value = diagnostics.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                result[key] = value
    return result


# ---------------------------------------------------------------------------
# Resume identity
# ---------------------------------------------------------------------------
#
# A durable result is identified by the Collection handoff key, which is stable for an
# immutable source revision. That is necessary and not sufficient: an answer produced
# with a different model, mode, prompt version or generation option is not the answer to
# the current question, even though the source is byte-identical. Issue #372 (upstream
# #287) binds the stored result to a fingerprint of the *effective* generation settings
# so a settings change invalidates the resume instead of silently returning a stale
# analysis as a duplicate.
#
# Compatibility rule: a row written before this guard existed carries no fingerprint and
# is treated as matching, so deploying the guard cannot trigger a mass re-analysis of a
# corpus already analysed. Everything written from this revision on carries one, and a
# mismatch is then a hard cache miss.


def result_matches_fingerprint(stored: Mapping[str, Any], wanted: str) -> bool:
    """Whether a stored result may be reused for the current generation settings.

    ``wanted == ""`` means the caller did not supply a fingerprint: presence is enough,
    which is the historical contract. A stored row with no fingerprint is legacy and is
    also treated as matching.
    """
    if not wanted:
        return True
    recorded = str(stored.get("generation_fingerprint") or "")
    return not recorded or recorded == wanted


def result_supersedes_fingerprint(stored: Mapping[str, Any] | None, new: str) -> bool:
    """Whether a new result should replace an existing one for the same source.

    Only a recorded, different, non-empty fingerprint supersedes: that is the case where
    the old result provably came from different generation settings. A legacy row without
    a fingerprint is kept, and an unchanged fingerprint is a duplicate.
    """
    if stored is None:
        return True
    recorded = str(stored.get("generation_fingerprint") or "")
    if not recorded or not new:
        return False
    return recorded != new


@dataclass(frozen=True, slots=True)
class TaskEnvelope:
    """One immutable unit of analysis work, identified by its idempotency key.

    ``record_ref`` is the canonical source identity (``source_url``), never a
    database primary key or a row number: that is what lets a resumed run recognise
    a task it has already completed. ``attempt`` travels inside the envelope rather
    than being mutated in the queue, so a retry is an explicit new message.
    """

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
    """A task handed to a worker together with the transport's message id.

    The id belongs to the transport (a Redis Stream entry, or a counter in an
    in-memory queue); the worker acknowledges *that* id, never the task.
    """

    message_id: str
    task: TaskEnvelope


class TaskQueue(Protocol):
    """Transport contract: publish work, claim it, and settle each claim.

    ``reclaim`` returns work whose consumer went silent. ``heartbeat`` records
    liveness out of band so a stalled worker is visible without its log.
    """

    def publish(self, task: TaskEnvelope) -> str: ...

    def claim(self) -> ClaimedTask | None: ...

    def reclaim(self, *, min_idle_ms: int) -> ClaimedTask | None: ...

    def ack(self, message_id: str) -> None: ...

    def dead_letter(self, task: TaskEnvelope, error: str) -> None: ...

    def heartbeat(self, **fields: str) -> None: ...


class DurableTaskStore(Protocol):
    """Result contract: idempotent writes keyed by source and generation settings.

    A store must distinguish completed, failed and terminally failed work. Terminal
    failures stop a permanently unanalysable record from retrying forever; the
    ``rearm_*`` methods let an operator decision (a larger output budget) reopen
    them deliberately.
    """

    def has_result(self, idempotency_key: str, fingerprint: str = "") -> bool: ...

    def has_terminal_failure(self, idempotency_key: str) -> bool: ...

    def rearm_terminal_failure(self, idempotency_key: str) -> int: ...

    def rearm_terminal_failure_if_budget_increased(
        self, idempotency_key: str, current_ceiling: int
    ) -> int: ...

    def failure_summary(self) -> dict[str, int]: ...

    def write_result(
        self,
        task: TaskEnvelope,
        result: Mapping[str, Any],
        provenance: Mapping[str, Any],
        *,
        fingerprint: str = "",
    ) -> bool: ...

    def write_failure(
        self,
        task: TaskEnvelope,
        error: str,
        provenance: Mapping[str, Any],
        diagnostics: Mapping[str, Any] | None = None,
        *,
        terminal: bool = False,
    ) -> None: ...
