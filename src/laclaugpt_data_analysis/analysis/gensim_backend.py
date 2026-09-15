"""Gensim topic-model baselines (LDA/LSI/HDP)."""
from __future__ import annotations

from typing import Iterable

from . import BackendUnavailable
from ..models import Provenance, Topic, TopicAssignment, TopicModelResult

_BACKEND = "gensim"


def is_available() -> bool:
    try:
        import gensim  # noqa: F401
        return True
    except ImportError:
        return False


def _version() -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version("gensim")
    except Exception:
        return ""


def discover(
    documents: Iterable[str], *, model: str | None = None,
    timestamps: list[str] | None = None, provenance: Provenance | None = None,
    n_topics: int = 8,
) -> TopicModelResult:
    if not is_available():
        raise BackendUnavailable("gensim is not installed")
    docs = [d for d in documents if d and d.strip()]
    method = (model or "gensim_lda").casefold()
    provenance_id = provenance.provenance_id if provenance else ""
    result = TopicModelResult(
        method=method,
        provenance_id=provenance_id,
        model_info={"library": "gensim", "library_version": _version(), "n_documents": len(docs)},
    )
    if not docs:
        return result
    from gensim import corpora
    from gensim.utils import simple_preprocess
    tokenized = [simple_preprocess(doc, deacc=True, min_len=2) for doc in docs]
    dictionary = corpora.Dictionary(tokenized)
    dictionary.filter_extremes(no_below=1 if len(docs) < 5 else 2, no_above=0.9, keep_n=10000)
    corpus = [dictionary.doc2bow(text) for text in tokenized]
    if not dictionary or not any(corpus):
        return result
    count = max(1, min(n_topics, len(dictionary)))
    if method == "gensim_lda":
        from gensim.models import LdaModel
        trained = LdaModel(corpus, id2word=dictionary, num_topics=count, random_state=42, passes=5)
    elif method == "gensim_lsi":
        from gensim.models import LsiModel
        trained = LsiModel(corpus, id2word=dictionary, num_topics=count)
    elif method == "gensim_hdp":
        from gensim.models import HdpModel
        trained = HdpModel(corpus, id2word=dictionary)
    else:
        raise ValueError(f"unknown gensim method: {method}")
    for topic_id, terms in trained.show_topics(formatted=False, num_topics=count, num_words=8):
        keywords = [word for word, _ in terms]
        topic_key = f"{method}_{topic_id}"
        result.topics.append(Topic(
            topic_id=topic_key,
            canonical_label=", ".join(keywords[:4]),
            aliases=keywords,
            description=f"{method} topic {topic_id}: {', '.join(keywords[:5])}",
            metadata={"method": method, "library_version": _version(), "provenance_id": provenance_id},
        ))
    for doc_index, bow in enumerate(corpus):
        for topic_id, score in trained.get_document_topics(bow, minimum_probability=0.05):
            result.assignments.append(TopicAssignment(
                target_id=f"document_{doc_index}",
                topic_id=f"{method}_{topic_id}",
                score=float(score),
                provenance_id=provenance_id,
            ))
    if timestamps:
        result.model_info["timestamps_supplied"] = True
    return result
