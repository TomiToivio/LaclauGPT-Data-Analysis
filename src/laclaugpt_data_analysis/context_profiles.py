"""Declarative context/memory profiles for analysis stages."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

PROFILE_NAMES = ("fast_local", "balanced", "high_accuracy", "validation")


@dataclass(frozen=True)
class ContextProfile:
    name: str
    description: str = ""
    context_memory: bool = True
    glossary_top_k: int = 5
    inject_codebook: bool = True
    inject_previous_batch_summary: bool = False
    inject_corpus_stats: bool = False
    inject_researcher_validation: bool = True
    inject_theory_context: bool = False
    vector_rag: bool = False
    max_context_chars: int = 6000
    max_records: int = 12
    max_tokens_hint: int = 1500
    context_provenance: bool = True
    fail_on_missing_codebook: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_BUNDLED = {
    "fast_local": ContextProfile(
        name="fast_local",
        description="Minimal local/pilot context with small deterministic budgets.",
        glossary_top_k=3,
        inject_previous_batch_summary=False,
        inject_corpus_stats=False,
        inject_researcher_validation=False,
        max_context_chars=2000,
        max_records=4,
        max_tokens_hint=500,
        context_provenance=False,
    ),
    "balanced": ContextProfile(
        name="balanced",
        description="Default bounded production context with provenance.",
        glossary_top_k=5,
        max_context_chars=6000,
        max_records=12,
        max_tokens_hint=1500,
    ),
    "high_accuracy": ContextProfile(
        name="high_accuracy",
        description="Deeper retrieval plus previous/corpus context for research runs.",
        glossary_top_k=8,
        inject_previous_batch_summary=True,
        inject_corpus_stats=True,
        inject_researcher_validation=True,
        inject_theory_context=True,
        vector_rag=True,
        max_context_chars=12000,
        max_records=24,
        max_tokens_hint=3000,
    ),
    "validation": ContextProfile(
        name="validation",
        description="Audit profile with deterministic bounded context and fail-closed codebooks.",
        glossary_top_k=5,
        inject_previous_batch_summary=True,
        inject_corpus_stats=True,
        inject_researcher_validation=True,
        inject_theory_context=True,
        vector_rag=True,
        max_context_chars=6000,
        max_records=12,
        max_tokens_hint=1500,
        fail_on_missing_codebook=True,
    ),
}


def load_context_profile(name: str) -> ContextProfile:
    try:
        return _BUNDLED[name]
    except KeyError as exc:
        raise KeyError(f"unknown context profile {name!r}; available: {sorted(_BUNDLED)}") from exc


def available_context_profiles() -> list[str]:
    return sorted(_BUNDLED)
