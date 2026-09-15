"""BERTopic topic-candidate backend.

Clusters are descriptive candidates, not discourse-theoretical conclusions.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import BackendUnavailable
from ..models import Provenance, Topic, TopicAssignment, TopicModelResult

_BACKEND = "bertopic"


def is_available() -> bool:
    try:
        import bertopic  # noqa: F401
        return True
    except ImportError:
        return False


def _version() -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version("bertopic")
    except Exception:
        return ""


def discover(
    documents: Iterable[str], *, model: str | None = None,
    language: str | None = None, timestamps: list[str] | None = None,
    provenance: Provenance | None = None,
) -> TopicModelResult:
    if not is_available():
        raise BackendUnavailable("bertopic is not installed")
    docs = [d for d in documents if d and d.strip()]
    if not docs:
        return TopicModelResult(method=_BACKEND, model_info={"documents": 0})
    from bertopic import BERTopic
    kwargs: dict[str, Any] = {"calculate_probabilities": True}
    if language:
        kwargs["language"] = language
    topic_model = BERTopic(**kwargs)
    topics, probs = topic_model.fit_transform(docs)
    provenance_id = provenance.provenance_id if provenance else ""
    result = TopicModelResult(
        method=_BACKEND,
        provenance_id=provenance_id,
        model_info={"library": "bertopic", "library_version": _version(), "n_documents": len(docs)},
    )
    for _, row in topic_model.get_topic_info().iterrows():
        topic_id = int(row["Topic"])
        if topic_id == -1:
            continue
        keywords = [word for word, _ in topic_model.get_topic(topic_id)[:8]]
        label = str(row.get("Name") or f"topic_{topic_id}")
        result.topics.append(Topic(
            topic_id=f"bertopic_{topic_id}",
            canonical_label=label.replace("_", " ").strip(),
            aliases=keywords,
            description=f"BERTopic cluster {topic_id}: {', '.join(keywords[:5])}",
            metadata={"method": _BACKEND, "library_version": _version(), "provenance_id": provenance_id},
        ))
    for doc_index, topic_id in enumerate(topics):
        if topic_id == -1:
            continue
        score = None
        if probs is not None:
            try:
                row = probs[doc_index]
                score = float(max(row)) if hasattr(row, "__len__") else float(row)
            except (TypeError, ValueError, IndexError):
                score = None
        result.assignments.append(TopicAssignment(
            target_id=f"document_{doc_index}",
            topic_id=f"bertopic_{topic_id}",
            score=score,
            provenance_id=provenance_id,
        ))
    if timestamps:
        result.model_info["topics_over_time_available"] = True
    return result
