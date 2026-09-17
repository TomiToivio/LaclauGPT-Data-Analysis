from laclaugpt_data_analysis.analysis import (
    BackendUnavailable,
    bertopic_backend,
    gensim_backend,
    sentence_transformers_backend,
    sklearn_backend,
    spacy_backend,
    statsmodels_backend,
    transformers_backend,
)
from laclaugpt_data_analysis.models import Provenance, Representation, Topic, TopicAssignment


def test_models_accept_backend_topic_metadata():
    topic = Topic(canonical_label="AI", metadata={"method": "test"})
    assignment = TopicAssignment(target_id="doc_1", topic_id=topic.topic_id, review_status="model_proposed")
    assert topic.metadata["method"] == "test"
    assert assignment.review_status == "model_proposed"


def test_provenance_and_representation_are_storage_neutral():
    provenance = Provenance(method="unit-test", model="synthetic")
    representation = Representation(source_id="source_1", text="Synthetic public test text", provenance_id=provenance.provenance_id)
    assert representation.provenance_id == provenance.provenance_id


def test_provenance_accepts_collection_handoff_fields_without_losing_evidence():
    provenance = Provenance.model_validate(
        {
            "provenance_id": "collection-prov-1",
            "stage": "collection",
            "collector": "laclaugpt-data-collection",
            "collector_version": "0.1.0",
            "captured_at": "2026-09-17T13:10:05.797645+00:00",
            "capture_id": "capture-1",
            "run_id": "ai26-distributed-001",
            "module": "rss-feedparser",
            "module_version": "1.2.3",
            "git_commit": "abc123",
            "visited_url": "https://www.lesswrong.com/feed.xml?view=frontpage",
            "api_url": "https://www.lesswrong.com/posts/example",
            "transformations": ["rss-atom-parse", "map-entry"],
            "metadata": {"existing": "kept"},
        }
    )

    assert provenance.provenance_id == "collection-prov-1"
    assert provenance.method == "rss-feedparser"
    assert provenance.created_at.isoformat() == "2026-09-17T13:10:05.797645+00:00"
    assert provenance.metadata["existing"] == "kept"
    assert provenance.metadata["collector_version"] == "0.1.0"
    assert provenance.metadata["capture_id"] == "capture-1"
    assert provenance.metadata["run_id"] == "ai26-distributed-001"
    assert provenance.metadata["module"] == "rss-feedparser"
    assert provenance.metadata["visited_url"].endswith("feed.xml?view=frontpage")
    assert provenance.metadata["transformations"] == ["rss-atom-parse", "map-entry"]


def test_optional_backends_import_without_optional_dependencies():
    for backend in (
        bertopic_backend,
        gensim_backend,
        sentence_transformers_backend,
        sklearn_backend,
        spacy_backend,
        statsmodels_backend,
        transformers_backend,
    ):
        assert isinstance(backend.is_available(), bool)


def test_backend_unavailable_is_runtime_error():
    assert issubclass(BackendUnavailable, RuntimeError)
