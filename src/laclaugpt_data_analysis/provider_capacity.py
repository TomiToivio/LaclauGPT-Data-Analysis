"""Provider capacity is not a document failure, and must not be paid for per task (#569).

On 2026-11-24 the AI26 worker lost a whole morning to a GPU-allocation conflict: every analysis call
ended in ``TransientProviderError: scheduler: no GPU capacity for gemma4:12b within 900s (status code:
503)``, three tasks paid that 900 s penalty in every cycle, and each cycle was killed at the 9000 s
ceiling and reported ``status=124`` — the same status a merely slow cycle gets. The journal could not
say "the provider had no capacity", and the cycle could not stop early.

Two things follow, and this module holds the vocabulary for both:

* **classify** the failure. ``no GPU capacity`` / a 503 from the scheduler / a model the endpoint does
  not have loaded are properties of the *provider*, not of the document. A capacity failure must not
  consume a document's retry budget, and it must not be retried inside the same cycle: the endpoint is
  not going to grow a GPU while the task waits again.
* **name** the outcome. A cycle that ended because the provider was unavailable exits ``75``
  (``EX_TEMPFAIL``) rather than ``0`` (nothing to do) or ``124`` (the wrapper's wall clock). Monitoring
  can then tell a capacity outage from a slow cycle, and the operator knows the fix is a GPU, not a
  document.

Nothing here changes what the analysis does; it changes how long the pipeline is willing to wait for a
provider that has already said no.
"""

from __future__ import annotations

import os

from .llm.base import LLMEmptyResponseError, LLMTruncationError, ProviderError

__all__ = [
    "CAPACITY_FAILURE_FIELD",
    "CAPACITY_OUTCOME",
    "EXIT_PROVIDER_UNAVAILABLE",
    "abort_after",
    "backoff_minutes",
    "capacity_reason",
    "is_capacity_unavailable",
]

#: Substrings that identify a capacity refusal rather than a transport blip. Lower-cased before matching.
#: The first is the observed Ollama scheduler message; the others are how the same condition appears when
#: the scheduler answers directly, when a model is not resident, and when a proxy reports it as a 503.
CAPACITY_MARKERS: tuple[str, ...] = (
    "no gpu capacity",
    "no capacity",
    "scheduler:",
    "model not loaded",
    "status code: 503",
    "503 service unavailable",
)

#: The outcome a worker records when it stops because the provider cannot serve requests.
CAPACITY_OUTCOME = "provider_unavailable"

#: ``EX_TEMPFAIL`` from ``sysexits.h``. Distinct from 0 (nothing to do), 1 (task failures), 3 (lock held)
#: and 124 (the wrapper's ceiling): a capacity outage is a temporary condition of the provider.
EXIT_PROVIDER_UNAVAILABLE = 75

#: The field a failure record carries when it was written because of capacity, so a later cycle can defer
#: the same task instead of paying for it again.
CAPACITY_FAILURE_FIELD = "capacity_unavailable"

#: Consecutive capacity failures that end a cycle. Two is enough: one may be a task that happened to hit a
#: reclaim window, two in a row means the endpoint is refusing.
DEFAULT_ABORT_AFTER = 2

#: How long a deferred task stays out of the ready set. Shorter than the recovery time of a GPU conflict in
#: practice, long enough that a cycle does not re-pay the 900 s scheduler timeout for the same document.
DEFAULT_BACKOFF_MINUTES = 30


def is_capacity_unavailable(exc: BaseException) -> bool:
    """Whether ``exc`` says the provider has no capacity, rather than something about the document.

    Deliberately narrow: a generic ``ProviderError`` is infrastructure trouble that may clear on a retry
    inside the same cycle (see ``INFRASTRUCTURE_REFUND_LIMIT``), whereas a capacity refusal will not clear
    until something outside the pipeline changes. Any ``ProviderError`` may carry a capacity message --
    the transports wrap the scheduler text differently -- but a length stop or an empty reply is never
    capacity, whatever its text says. Truncation and empty responses are never capacity: they
    are properties of the generation.
    """
    if not isinstance(exc, ProviderError):
        return False
    if isinstance(exc, (LLMTruncationError, LLMEmptyResponseError)):
        # A length stop or an empty reply is a property of the generation; it must keep its own
        # escalation ladder even if the message happens to mention capacity.
        return False
    message = str(exc).lower()
    return any(marker in message for marker in CAPACITY_MARKERS)


def capacity_reason(exc: BaseException) -> str | None:
    """The marker that made this failure a capacity failure, normalised for a log line.

    Naming the signal (``no_gpu_capacity``, ``scheduler``, ``model_not_loaded``) matters because the same
    outage reaches the pipeline in several shapes, and an operator diagnosing the endpoint needs to know
    which one this cycle saw.
    """
    if not is_capacity_unavailable(exc):
        return None
    message = str(exc).lower()
    for marker in CAPACITY_MARKERS:
        if marker in message:
            return marker.strip(":").replace(" ", "_")
    return "capacity"  # pragma: no cover - is_capacity_unavailable already proved a match


def abort_after() -> int:
    """How many consecutive capacity failures end a cycle (``LACLAUGPT_AI26_PROVIDER_ABORT_AFTER``)."""
    return _positive_int(os.environ.get("LACLAUGPT_AI26_PROVIDER_ABORT_AFTER"), DEFAULT_ABORT_AFTER)


def backoff_minutes() -> int:
    """How long a capacity-deferred task stays out of the ready set, in minutes."""
    return _positive_int(
        os.environ.get("LACLAUGPT_AI26_CAPACITY_BACKOFF_MINUTES"), DEFAULT_BACKOFF_MINUTES
    )


def _positive_int(raw: str | None, default: int) -> int:
    if not raw or not raw.strip().isdigit():
        return default
    value = int(raw.strip())
    return value if value > 0 else default
