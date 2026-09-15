"""SentenceTransformers backend ported from the public LaclauGPT core."""
from __future__ import annotations

import math
from typing import Any, Iterable

from . import BackendUnavailable
from ..models import EmbeddingResult

_BACKEND = "sentence_transformers"
_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
_ENGINES: dict[str, Any] = {}


def is_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _engine(model: str):
    if not is_available():
        raise BackendUnavailable("sentence-transformers is not installed")
    if model not in _ENGINES:
        from sentence_transformers import SentenceTransformer
        _ENGINES[model] = SentenceTransformer(model)
    return _ENGINES[model]


def _version() -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version("sentence-transformers")
    except Exception:
        return ""


def embed(
    texts: Iterable[str], *, model: str | None = None, item_ids: list[str] | None = None
) -> list[EmbeddingResult]:
    model = model or _DEFAULT_MODEL
    values = list(texts)
    vectors = _engine(model).encode(values, normalize_embeddings=True)
    return [
        EmbeddingResult(
            item_id=item_ids[index] if item_ids else text,
            vector=[float(x) for x in vector],
            model=model,
            model_version=_version(),
            backend=_BACKEND,
            dimensions=len(vector),
        )
        for index, (text, vector) in enumerate(zip(values, vectors, strict=True))
    ]


def similarity(text_a: str, text_b: str, *, model: str | None = None) -> float:
    results = embed([text_a, text_b], model=model)
    a, b = results[0].vector, results[1].vector
    denominator = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return 0.0 if not denominator else sum(x * y for x, y in zip(a, b, strict=True)) / denominator
