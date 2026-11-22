"""Controlled, provisional AI26 formation labels (#454)."""

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.formation_vocabulary import (
    FORMATION_LABELS,
    FORMATION_VOCABULARY_VERSION,
    normalize_formation_label,
)
from laclaugpt_data_analysis.stages.postprocess import _objects
from laclaugpt_data_analysis.stages.proposals import DiscursiveElement


def test_known_aliases_collapse_without_guessing() -> None:
    assert normalize_formation_label("Critical AI") == ("critical_ai", True)
    assert normalize_formation_label("critical_ai") == ("critical_ai", True)
    assert normalize_formation_label("AI doomerism") == ("existential_risk", True)
    assert normalize_formation_label("left-wing accelerationism") == (
        "left_accelerationist", True
    )
    assert normalize_formation_label("Automated Gatekeeping") == ("unknown", False)
    assert normalize_formation_label("techno-optimism") == ("unknown", False)
    assert "other" not in FORMATION_LABELS


def test_formation_projection_preserves_original_and_provisionality() -> None:
    record = CanonicalRecord(source_url="https://example.org/ai26-formation")
    records = _objects(
        record,
        [
            DiscursiveElement(label="Critical AI"),
            DiscursiveElement(label="Automated Gatekeeping"),
        ],
        "formation",
    )
    assert [item.label for item in records] == ["critical_ai", "unknown"]
    assert records[0].description is None
    assert records[1].description == "Automated Gatekeeping"
    assert records[1].metadata["original_formation_label"] == "Automated Gatekeeping"
    assert records[1].metadata["requires_label_review"] is True
    assert all(item.review_status == "PROVISIONAL" for item in records)
    assert all(item.metadata["corpus_validation_required"] for item in records)
    assert all(
        item.metadata["formation_vocabulary_version"] == FORMATION_VOCABULARY_VERSION
        for item in records
    )
