"""scikit-learn baselines for topic discovery and supervised validation."""
from __future__ import annotations

from typing import Any, Iterable

from . import BackendUnavailable
from ..models import Provenance, Topic, TopicAssignment, TopicModelResult

_BACKEND = "sklearn"


def is_available() -> bool:
    try:
        import sklearn  # noqa: F401
        return True
    except ImportError:
        return False


def _version() -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version("scikit-learn")
    except Exception:
        return ""


def discover(
    documents: Iterable[str], *, model: str | None = None,
    timestamps: list[str] | None = None, provenance: Provenance | None = None,
    n_topics: int = 8,
) -> TopicModelResult:
    if not is_available():
        raise BackendUnavailable("scikit-learn is not installed")
    docs = [d for d in documents if d and d.strip()]
    method = (model or "sklearn_nmf").casefold()
    provenance_id = provenance.provenance_id if provenance else ""
    result = TopicModelResult(
        method=method,
        provenance_id=provenance_id,
        model_info={"library": "scikit-learn", "library_version": _version(), "n_documents": len(docs)},
    )
    if len(docs) < 2:
        return result
    from sklearn.feature_extraction.text import TfidfVectorizer
    vectorizer = TfidfVectorizer(max_features=5000, stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(docs)
    feature_names = vectorizer.get_feature_names_out()
    components_count = max(1, min(n_topics, matrix.shape[0], matrix.shape[1]))

    if method == "sklearn_nmf":
        from sklearn.decomposition import NMF
        trained = NMF(n_components=components_count, random_state=42, init="nndsvda")
        weights = trained.fit_transform(matrix)
        components = trained.components_
        memberships = None
    elif method == "sklearn_kmeans":
        from sklearn.cluster import KMeans
        trained = KMeans(n_clusters=components_count, random_state=42, n_init=10)
        memberships = trained.fit_predict(matrix)
        components = trained.cluster_centers_
        weights = None
    else:
        raise ValueError(f"unknown sklearn topic method: {method}")

    for topic_id, component in enumerate(components):
        top = component.argsort()[::-1][:8]
        keywords = [str(feature_names[i]) for i in top if component[i] > 0]
        if not keywords:
            continue
        topic_key = f"{method}_{topic_id}"
        result.topics.append(Topic(
            topic_id=topic_key,
            canonical_label=", ".join(keywords[:4]),
            aliases=keywords,
            description=f"{method} topic {topic_id}: {', '.join(keywords[:5])}",
            metadata={"method": method, "library_version": _version(), "provenance_id": provenance_id},
        ))
        for doc_index in range(len(docs)):
            if method == "sklearn_nmf":
                score = float(weights[doc_index][topic_id])
                if score < 0.05:
                    continue
            else:
                if int(memberships[doc_index]) != topic_id:
                    continue
                score = None
            result.assignments.append(TopicAssignment(
                target_id=f"document_{doc_index}", topic_id=topic_key,
                score=score, provenance_id=provenance_id,
            ))
    if timestamps:
        result.model_info["timestamps_supplied"] = True
    return result


def tfidf_baseline(
    train_texts: list[str], train_labels: list[str], test_texts: list[str],
    *, test_labels: list[str] | None = None, classifier: str = "logreg",
) -> dict[str, Any]:
    """Fit a cheap classical baseline; metrics are returned when test labels exist."""
    if not is_available():
        raise BackendUnavailable("scikit-learn is not installed")
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import MultinomialNB
    from sklearn.svm import LinearSVC
    classifiers = {
        "logreg": LogisticRegression(max_iter=1000),
        "naive_bayes": MultinomialNB(),
        "linear_svc": LinearSVC(),
    }
    if classifier not in classifiers:
        raise ValueError(f"unknown classifier: {classifier}")
    vectorizer = TfidfVectorizer(max_features=5000)
    features = vectorizer.fit_transform(train_texts)
    trained = classifiers[classifier].fit(features, train_labels)
    predictions = [str(x) for x in trained.predict(vectorizer.transform(test_texts))]
    output: dict[str, Any] = {
        "classifier": classifier, "sklearn_version": _version(), "predictions": predictions,
    }
    if test_labels is not None:
        from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support
        precision, recall, f1, _ = precision_recall_fscore_support(
            test_labels, predictions, average="weighted", zero_division=0,
        )
        output.update({
            "precision": float(precision), "recall": float(recall), "f1": float(f1),
            "f1_check": float(f1_score(test_labels, predictions, average="weighted", zero_division=0)),
            "confusion_matrix": confusion_matrix(test_labels, predictions).tolist(),
        })
    return output
