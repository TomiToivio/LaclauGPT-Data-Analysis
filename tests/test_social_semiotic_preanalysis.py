from __future__ import annotations

from difflib import SequenceMatcher

import pytest
from pydantic import ValidationError

from laclaugpt_data_analysis.social_semiotic import (
    PROHIBITED_PREANALYSIS_KEYS,
    EvidencePointer,
    IntermodalRelation,
    MultimodalSummaryProposal,
    SemioticResource,
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



def test_evidence_pointer_normalises_null_optional_fields_and_known_source_ref_typo() -> None:
    item = MultimodalSummaryProposal.model_validate(
        {
            "evidence": [
                {
                    "evidence_id": "text:legacy:1",
                    "modality": "linguistic",
                    "source__ref": "content.text",
                    "exact_text": None,
                    "frame_id": None,
                    "uncertainty": "Legacy-derived text has no frame pointer.",
                }
            ]
        }
    )

    pointer = item.evidence[0]
    assert pointer.source_ref == "content.text"
    assert pointer.exact_text == ""
    assert pointer.frame_id == ""
    assert pointer.uncertainty == "Legacy-derived text has no frame pointer."


def test_evidence_pointer_still_rejects_unknown_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EvidencePointer.model_validate(
            {
                "evidence_id": "text:1",
                "modality": "linguistic",
                "source___ref": "content.text",
            }
        )


def test_taxonomy_literals_normalise_nulls_and_unambiguous_near_misses() -> None:
    item = MultimodalSummaryProposal.model_validate(
        {
            "modalities_present": ["typography", "visual", None, "lingustic"],
            "semiotic_resources": [
                {
                    "mode": None,
                    "description": "Synthetic resource reconstructed from a stored failure.",
                    "confidence": "medum",
                }
            ],
            "salient_signs": [
                {
                    "sign_id": "sign:synthetic:1",
                    "source_form": "synthetic",
                    "modes": ["lingustic", None],
                    "confidence": None,
                }
            ],
        }
    )

    assert item.modalities_present == ["typographic", "visual", "linguistic"]
    assert item.semiotic_resources[0].mode == "other"
    assert item.semiotic_resources[0].confidence == "medium"
    assert item.salient_signs[0].modes == ["linguistic"]
    assert item.salient_signs[0].confidence == "unknown"


def test_taxonomy_literals_do_not_guess_distant_values() -> None:
    with pytest.raises(ValidationError):
        MultimodalSummaryProposal.model_validate({"modalities_present": ["zoological"]})


def test_taxonomy_tolerance_keeps_required_fields_and_types_strict() -> None:
    with pytest.raises(ValidationError):
        SemioticResource.model_validate({"mode": "visual"})

    with pytest.raises(ValidationError):
        SemioticResource.model_validate({"mode": "visual", "description": None})

    with pytest.raises(ValidationError):
        SemioticResource.model_validate({"mode": {"unexpected": "shape"}, "description": "x"})


def test_prohibited_boundary_keys_are_outside_literal_similarity_floor() -> None:
    allowed_fields = set(MultimodalSummaryProposal.model_fields)
    highest = max(
        SequenceMatcher(None, prohibited, allowed).ratio()
        for prohibited in PROHIBITED_PREANALYSIS_KEYS
        for allowed in allowed_fields
    )
    assert highest < 0.85

    with pytest.raises(ValueError):
        assert_preanalysis_boundary({"political_subjects": ["synthetic"]})


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
