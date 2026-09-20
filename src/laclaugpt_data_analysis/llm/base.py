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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LLMResponse:
    """One completed provider call."""

    content: str
    provenance: LLMCallProvenance


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
        """Backward-compatible alias for the provider-neutral user field."""
        return self.user


class ProviderError(RuntimeError):
    """Raised when a provider cannot complete a call."""


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