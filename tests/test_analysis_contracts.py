from laclaugpt_data_analysis.analysis import BackendUnavailable
from laclaugpt_data_analysis.analysis import bertopic_backend, gensim_backend, sentence_transformers_backend
from laclaugpt_data_analysis.analysis import sklearn_backend, spacy_backend, statsmodels_backend, transformers_backend
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
