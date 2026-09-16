from pathlib import Path

import pytest

from laclaugpt_data_analysis.analysis.luhmann import (
    CrossSystemTranslation,
    EvidenceSpan,
    SystemsAnalysis,
    baseline_to_analysis,
    build_structured_extraction_prompt,
    contingency_matrix,
    load_codebook,
    mutual_information,
    prototype_classify,
    shannon_entropy,
    translation_edges,
)
from laclaugpt_data_analysis.config import Settings


CODEBOOK = Path("codebooks/public/luhmann_social_systems_v1.yaml")


def test_luhmann_feature_is_disabled_by_default() -> None:
    settings = Settings()
    assert settings.luhmann_enabled is False


def test_public_codebook_loads_and_includes_core_systems() -> None:
    codebook = load_codebook(CODEBOOK)
    ids = {item.id for item in codebook.systems}
    assert codebook.version.startswith("1.0.0")
    assert {"politics", "law", "science", "economy", "mass_media"} <= ids


def test_non_llm_prototype_baseline_is_multilabel_and_transparent() -> None:
    codebook = load_codebook(CODEBOOK)
    text = (
        "A new research study benchmarks the model and parliament debates regulation "
        "and public policy based on the scientific evidence."
    )
    scores = prototype_classify(text, codebook, top_k=4)
    labels = {item.system for item in scores}
    assert "science" in labels
    assert "politics" in labels or "law" in labels
    assert all(0.0 <= item.score <= 1.0 for item in scores)

    analysis = baseline_to_analysis(text, codebook, source_record_id="synthetic-1")
    assert analysis.primary_system in labels
    assert analysis.model_method == "prototype-term-overlap-v1"
    assert analysis.provenance["source_record_id"] == "synthetic-1"


def test_structured_prompt_permits_uncertainty() -> None:
    codebook = load_codebook(CODEBOOK)
    prompt = build_structured_extraction_prompt("Synthetic communication", codebook)
    assert "Do not force a single" in prompt
    assert "unknown" in prompt
    assert "evidence spans" in prompt


def test_information_theory_helpers() -> None:
    assert shannon_entropy(["science", "science", "politics", "politics"]) == pytest.approx(1.0)
    assert shannon_entropy([]) == 0.0

    independent = [("a", "x"), ("a", "y"), ("b", "x"), ("b", "y")]
    assert mutual_information(independent) == pytest.approx(0.0)

    coupled = [("a", "x"), ("a", "x"), ("b", "y"), ("b", "y")]
    assert mutual_information(coupled) == pytest.approx(1.0)

    assert contingency_matrix(coupled) == {"a": {"x": 2}, "b": {"y": 2}}


def test_translation_edges_retain_evidence_and_provenance() -> None:
    analysis = SystemsAnalysis(
        primary_system="science",
        referenced_systems=["science", "politics"],
        model_method="human-coded-test",
        provenance={"codebook_version": "test"},
        cross_system_translations=[
            CrossSystemTranslation(
                source_system="science",
                target_system="politics",
                relation="translated_as",
                confidence=0.8,
                evidence_spans=[
                    EvidenceSpan(
                        text="research result becomes a policy claim",
                        source_record_id="r1",
                    )
                ],
            )
        ],
    )
    rows = translation_edges([("r1", analysis)])
    assert rows[0]["source_record_id"] == "r1"
    assert rows[0]["source_system"] == "science"
    assert rows[0]["target_system"] == "politics"
    assert rows[0]["evidence_spans"][0]["source_record_id"] == "r1"
    assert rows[0]["provenance"]["codebook_version"] == "test"
