from __future__ import annotations

import pytest
from pydantic import ValidationError

from laclaugpt_data_analysis.social_semiotic import (
    EvidencePointer,
    IntermodalRelation,
    MultimodalSummaryProposal,
    SignObservation,
    UncertaintyObservation,
    assert_preanalysis_boundary,
)


def test_schema_handles_text_only_and_preserves_source_form() -> None:
    item = MultimodalSummaryProposal(
        source_languages=["fi"],
        modalities_present=["linguistic"],
        modalities_missing=["visual", "auditory"],
        evidence=[
            EvidencePointer(
                evidence_id="text:1",
                modality="linguistic",
                source_ref="content.text",
                exact_text="#tekoäly nyt",
                confidence="high",
            )
        ],
        salient_signs=[
            SignObservation(
                sign_id="sign:1",
                source_form="#tekoäly",
                modes=["linguistic"],
                evidence_ids=["text:1"],
                confidence="high",
            )
        ],
        limitations=["No image or audio was supplied."],
    )
    assert item.salient_signs[0].source_form == "#tekoäly"
    assert item.modalities_missing == ["visual", "auditory"]


def test_cross_modal_conflict_survives_in_schema() -> None:
    item = MultimodalSummaryProposal(
        modalities_present=["linguistic", "visual"],
        intermodal_relations=[
            IntermodalRelation(
                relation_type="conflict",
                modes=["linguistic", "visual"],
                description="Caption states X while the chart label states Y.",
                evidence_ids=["caption:1", "frame:7"],
                confidence="high",
            )
        ],
    )
    assert item.intermodal_relations[0].relation_type == "conflict"


def test_uncertain_ocr_is_explicit() -> None:
    item = MultimodalSummaryProposal(
        uncertainty=[
            UncertaintyObservation(
                category="ocr",
                description="Final word may be model or models.",
                affected_evidence_ids=["ocr:4"],
                confidence="low",
            )
        ]
    )
    assert item.uncertainty[0].category == "ocr"


def test_extra_political_classification_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MultimodalSummaryProposal.model_validate({"summary": "description", "populism": True})


@pytest.mark.parametrize(
    "key",
    [
        "nodal_points", "floating_signifiers", "empty_signifiers", "antagonisms",
        "frontiers", "ideology", "political_alignment", "hegemony",
        "political_demands", "sentiment",
    ],
)
def test_boundary_guard_rejects_downstream_fields(key: str) -> None:
    with pytest.raises(ValueError):
        assert_preanalysis_boundary({"preanalysis": {"nested": {key: ["x"]}}})


def test_source_word_populism_is_allowed_as_evidence_not_classification() -> None:
    item = MultimodalSummaryProposal(
        evidence=[
            EvidencePointer(
                evidence_id="text:2",
                modality="linguistic",
                exact_text="The source literally uses the word populism.",
                confidence="high",
            )
        ]
    )
    assert "populism" in item.evidence[0].exact_text
