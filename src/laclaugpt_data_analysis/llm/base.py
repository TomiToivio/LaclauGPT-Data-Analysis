"""Provider-neutral LLM runtime contracts.

The analysis package treats the LLM as an interchangeable backend: pipeline
stages depend on the small :class:`LLMProvider` protocol, never on Ollama
directly. Importing this package performs no network calls and requires no
optional dependency; ``ollama`` is imported lazily inside the Ollama provider.

Provenance discipline: every call records which model actually answered, on
which endpoint, and whether an authorised fallback was used. Model-reported
confidence is an uncalibrated self-report and stays separate from evidence
verification and human review (THEORY.md invariants INV_HUMAN_REVIEW).
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, runtime_checkable

DEFAULT_OPTIONS: dict[str, Any] = {
    "repeat_last_n": 64,
    "repeat_penalty": 1.1,
    "num_ctx": 8192,
    "top_p": 0.9,
    "top_k": 40,
    "min_p": 0.0,
    "temperature": 0.0,
    "num_predict": 2048,
}


@dataclass(frozen=True)
class LLMCallProvenance:
    """Where one model answer actually came from."""

    requested_mode: str
    requested_model: str
    resolved_model: str
    actual_mode: str
    actual_model: str
    actual_model_digest: str = ""
    endpoint: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""
    #: Provider calls made for this answer. >1 means the first answer was empty and
    #: was retried (issue #372); the record says so instead of hiding it.
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LLMResponse:
    """One completed provider call with provider termination metadata."""

    content: str
    provenance: LLMCallProvenance
    finish_reason: str = ""
    truncated: bool = False


@dataclass(frozen=True)
class ChatRequest:
    """A complete provider request.

    ``images`` contains provider-readable local image paths or equivalent image
    references. It remains empty for text-only calls so existing providers stay
    source-compatible while multimodal adapters can prove which pixels were attached.
    """

    model: str
    system: str
    user: str
    options: dict[str, Any] = field(default_factory=dict)
    schema: dict[str, Any] | None = None
    allow_cloud_fallback: bool | None = None
    images: tuple[str, ...] = ()

    @property
    def user_prompt(self) -> str:
        """Backward-compatible view of the historical user-prompt contract."""
        return self.user.replace("[CONTEXT MEMORY]", "[MEMORY CONTEXT]")


class ProviderError(RuntimeError):
    """Raised when a provider cannot complete a call."""


class LLMTruncationError(ProviderError):
    """Raised when a provider stops because the generation budget was exhausted."""


class LLMEmptyResponseError(ProviderError):
    """Raised when a provider kept answering HTTP 200 with no usable content.

    A blank completion is not a valid analysis of anything. It used to be returned as a
    normal answer, which let a stage store an empty description or cache an empty output
    as a success (issue #372, upstream #274). It is now a loud, typed failure.
    """


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal provider boundary used by the pipeline stages."""

    def chat(self, request: ChatRequest) -> LLMResponse:
        """Return one completion with provenance."""
        ...


def merge_options(extra: dict[str, Any] | None) -> dict[str, Any]:
    """Deterministic option merge over the deterministic defaults."""
    options = dict(DEFAULT_OPTIONS)
    if extra:
        options.update(extra)
    return options


#: How many extra attempts a provider makes when a call succeeds (HTTP 200) but returns
#: no usable content. Set to 0 to disable the retry and fail on the first blank answer.
EMPTY_RESPONSE_RETRIES_ENV = "LACLAUGPT_EMPTY_RESPONSE_RETRIES"
EMPTY_RESPONSE_MAX_RETRIES = 3


def empty_response_retries() -> int:
    """Bounded, environment-controlled retry count for blank-but-successful answers."""
    raw = os.environ.get(EMPTY_RESPONSE_RETRIES_ENV, "").strip()
    if not raw:
        return 2
    try:
        value = int(raw)
    except ValueError:
        return 2
    return max(0, min(EMPTY_RESPONSE_MAX_RETRIES, value))


#: Environment prefix for generation settings recorded in the fingerprint.
GENERATION_FINGERPRINT_VERSION = 1


def effective_generation_settings(
    *,
    model: str,
    options: dict[str, Any] | None = None,
    mode: str = "",
    prompt_version: str = "",
    prompt_sha256: str = "",
) -> dict[str, Any]:
    """Describe the generation settings that will *actually* be in force.

    ``options`` is merged over :data:`DEFAULT_OPTIONS`, so a changed default is a changed
    setting even when the caller passed nothing. Every value is normalised to a string so
    the description hashes identically across processes and JSON encoders.
    """
    merged = merge_options(dict(options or {}))
    return {
        "fingerprint_format": GENERATION_FINGERPRINT_VERSION,
        "model": str(model or ""),
        "mode": str(mode or ""),
        "options": {str(key): str(value) for key, value in sorted(merged.items())},
        "prompt_version": str(prompt_version or ""),
        "prompt_sha256": str(prompt_sha256 or ""),
    }


def generation_fingerprint(**settings: Any) -> str:
    """A stable hash of the effective generation settings.

    This is the resume/idempotency identity of a model answer. It deliberately covers the
    model, the resolved mode, every effective generation option (defaults included) and
    the prompt identity, because an answer produced under different settings is not the
    answer to the current question even when the source record is identical (issue #372,
    upstream #287).
    """
    payload = effective_generation_settings(**settings)
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def configured_model_override() -> str:
    """The model named by the environment, if any. Read-only, no network."""
    return (
        os.environ.get("LACLAUGPT_LLM_MODEL")
        or os.environ.get("LACLAUGPT_OLLAMA_MODEL")
        or os.environ.get("OLLAMA_MODEL")
        or ""
    )