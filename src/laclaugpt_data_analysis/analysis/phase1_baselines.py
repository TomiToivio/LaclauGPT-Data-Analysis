"""Optional Phase-1 descriptive NLP baselines.

These helpers lazy-import third-party libraries and are not registered in the
default analysis pipeline. They provide comparison baselines for researchers,
not Laclaudian interpretation. Installing the base package never imports these
dependencies, downloads models, or performs network access.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Sequence


class OptionalBaselineDependencyError(RuntimeError):
    """Raised when an explicitly requested Phase-1 baseline is not installed."""


def _optional_module(name: str, *, extra: str = "phase1-nlp") -> Any:
    try:
        return import_module(name)
    except ImportError as exc:
        raise OptionalBaselineDependencyError(
            f"Optional baseline dependency {name!r} is not installed. "
            f"Install with: pip install -e '.[{extra}]'"
        ) from exc


@dataclass(frozen=True, slots=True)
class KeywordCandidate:
    term: str
    score: float
    backend: str
    interpretation_status: str = "DESCRIPTIVE_ONLY"

    def as_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "score": self.score,
            "backend": self.backend,
            "interpretation_status": self.interpretation_status,
        }


def yake_keywords(
    text: str,
    *,
    language: str = "en",
    top_n: int = 10,
    max_ngram_size: int = 3,
) -> list[KeywordCandidate]:
    """Return YAKE keyword candidates, preserving YAKE's native score direction."""
    yake = _optional_module("yake")
    extractor = yake.KeywordExtractor(lan=language, n=max_ngram_size, top=top_n)
    return [
        KeywordCandidate(term=str(term), score=float(score), backend="yake")
        for term, score in extractor.extract_keywords(text)
    ]


def keybert_keywords(
    text: str,
    *,
    model: Any,
    top_n: int = 10,
    keyphrase_ngram_range: tuple[int, int] = (1, 3),
) -> list[KeywordCandidate]:
    """Return KeyBERT candidates using an explicitly supplied embedding model."""
    keybert = _optional_module("keybert")
    extractor = keybert.KeyBERT(model=model)
    rows = extractor.extract_keywords(
        text,
        keyphrase_ngram_range=keyphrase_ngram_range,
        top_n=top_n,
    )
    return [
        KeywordCandidate(term=str(term), score=float(score), backend="keybert")
        for term, score in rows
    ]


def textacy_terms(
    doc: Any,
    *,
    top_n: int = 10,
    algorithm: str = "textrank",
) -> list[KeywordCandidate]:
    """Return textacy terms from a caller-prepared spaCy Doc."""
    textacy = _optional_module("textacy")
    keyterms = textacy.extract.keyterms
    algorithm_fn = getattr(keyterms, algorithm)
    rows = algorithm_fn(doc, topn=top_n)
    return [
        KeywordCandidate(term=str(term), score=float(score), backend=f"textacy:{algorithm}")
        for term, score in rows
    ]


def available_backends() -> tuple[str, ...]:
    return ("textacy", "yake", "keybert")


def corpus_yake_keywords(
    texts: Sequence[str],
    *,
    language: str = "en",
    top_n: int = 10,
) -> list[list[KeywordCandidate]]:
    return [yake_keywords(text, language=language, top_n=top_n) for text in texts]
