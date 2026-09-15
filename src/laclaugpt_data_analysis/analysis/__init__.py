"""Backend-neutral analytical interfaces.

Descriptive features, embeddings, clusters and statistical results are evidence
for interpretation, not automatic discourse-theoretical conclusions.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable

from ..models import (
    ClassificationResult,
    EmbeddingResult,
    NlpDocument,
    Representation,
    TopicModelResult,
)


class BackendUnavailable(RuntimeError):
    """Raised when an optional analytical dependency is not installed."""


@runtime_checkable
class NLPBackend(Protocol):
    def is_available(self) -> bool: ...
    def analyze(self, representation: Representation, model_name: str | None = None) -> NlpDocument: ...


@runtime_checkable
class EmbeddingBackend(Protocol):
    def is_available(self) -> bool: ...
    def embed(self, texts: Iterable[str], *, model: str | None = None) -> list[EmbeddingResult]: ...
    def similarity(self, text_a: str, text_b: str, **kwargs: Any) -> float: ...


@runtime_checkable
class TopicModelBackend(Protocol):
    def is_available(self) -> bool: ...
    def discover(self, documents: Iterable[str], *, model: str | None = None, timestamps: list[str] | None = None) -> TopicModelResult: ...


@runtime_checkable
class ClassificationBackend(Protocol):
    def is_available(self) -> bool: ...
    def classify(self, text: str, *, task: str, model: str | None = None) -> ClassificationResult: ...


@runtime_checkable
class StatisticsBackend(Protocol):
    def is_available(self) -> bool: ...
    def fit(self, dataset: Any, *, formula: str | None = None, method: str = "ols", **options: Any) -> dict[str, Any]: ...
