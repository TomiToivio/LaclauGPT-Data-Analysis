"""Regression coverage for issue #296.

Pre-analysis asks a local model to echo a seeded skeleton, so it predictably emits
``null`` for optional fields it has nothing to say about and near-miss spellings of
both keys and taxonomy values.  Each of these terminated a record that was otherwise
usable, burning a full model round trip; #296 was the blocker for the Phase 1
Analysis -> Visualization gate.

The payloads below are reconstructed from the stored ``ai26__analysis_failures``
error texts (sanitized): ``evidence.N.frame_id`` -> None (string_type),
``modalities_present.N`` / ``semiotic_resources.N.mode`` -> None or a typo
(literal_error), and ``evidence.N.source__ref`` (extra_forbidden).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from laclaugpt_data_analysis.social_semiotic import (
    EvidencePointer,
    MultimodalSummaryProposal,
    SignObservation,
    assert_preanalysis_boundary,
)

# ------------------------------------------------ the three observed failures


def test_null_evidence_frame_id_validates_and_keeps_the_evidence() -> None:
    """`frame_id: null` on non-frame-derived evidence: the observed #296 failure."""
    proposal = MultimodalSummaryProposal.model_validate(
        {
            "evidence": [
                {"evidence_id": "e1", "modality": "linguistic", "frame_id": None},
                {"evidence_id": "e2", "modality": "visual", "frame_id": None},
            ]
        }
    )
    assert [pointer.frame_id for pointer in proposal.evidence] == ["", ""]
    # The evidence itself must be preserved, not dropped along with the null.
    assert [pointer.evidence_id for pointer in proposal.evidence] == ["e1", "e2"]


def test_null_evidence_frame_id_uses_the_declared_default() -> None:
    pointer = EvidencePointer.model_validate(
        {"evidence_id": "e1", "modality": "linguistic", "frame_id": None}
    )
    assert pointer.frame_id == ""
    assert pointer.source_ref == ""
    assert pointer.exact_text == ""


def test_misspelled_evidence_key_is_absorbed() -> None:
    """`source__ref` (double underscore) was rejected as an extra input."""
    pointer = EvidencePointer.model_validate(
        {"evidence_id": "e1", "modality": "linguistic", "source__ref": "body_text"}
    )
    assert pointer.source_ref == "body_text"


def test_misspelled_modality_value_is_absorbed() -> None:
    """The model produced 'typography' and 'lingustic' in production."""
    proposal = MultimodalSummaryProposal.model_validate(
        {"modalities_present": ["typography", "lingustic"]}
    )
    assert proposal.modalities_present == ["typographic", "linguistic"]


def test_null_literal_becomes_the_unclassified_member() -> None:
    """A null enum means 'did not classify', which the taxonomy already expresses."""
    proposal = MultimodalSummaryProposal.model_validate(
        {"semiotic_resources": [{"mode": None, "description": "unclassified"}]}
    )
    assert proposal.semiotic_resources[0].mode == "other"


def test_null_element_inside_a_literal_list_is_dropped() -> None:
    proposal = MultimodalSummaryProposal.model_validate(
        {"modalities_present": ["visual", None, "linguistic"]}
    )
    assert proposal.modalities_present == ["visual", "linguistic"]


def test_nulls_inside_a_nested_required_literal_list_validate() -> None:
    """`salient_signs.N.modes.N` -> None was an observed literal_error."""
    observation = SignObservation.model_validate(
        {"sign_id": "s1", "source_form": "logo", "modes": ["visual", None]}
    )
    assert observation.modes == ["visual"]


# ------------------------------------------------------- strictness must survive


def test_genuinely_unknown_key_is_still_rejected() -> None:
    """Tolerating near-miss *formatting* must not open the schema to new fields."""
    with pytest.raises(ValidationError):
        EvidencePointer.model_validate(
            {"evidence_id": "e1", "modality": "linguistic", "political_alignment": "x"}
        )


def test_unknown_key_far_from_every_field_is_still_rejected() -> None:
    with pytest.raises(ValidationError):
        MultimodalSummaryProposal.model_validate({"totally_bogus_key": 1})


def test_missing_required_field_is_still_rejected() -> None:
    with pytest.raises(ValidationError):
        EvidencePointer.model_validate({"modality": "linguistic"})


def test_null_on_a_required_non_literal_field_is_still_rejected() -> None:
    """A required identifier cannot be silently blanked."""
    with pytest.raises(ValidationError):
        EvidencePointer.model_validate(
            {"evidence_id": None, "modality": "linguistic"}
        )


def test_enum_value_far_from_every_option_is_still_rejected() -> None:
    """A value the model genuinely chose but the taxonomy lacks must not be guessed.

    'zoological' is not close to any member of Mode, so mapping it onto one would
    fabricate a category.  It must fail and trigger the validation-aware retry.
    """
    with pytest.raises(ValidationError):
        MultimodalSummaryProposal.model_validate({"modalities_present": ["zoological"]})


def test_wrong_type_on_a_literal_is_still_rejected() -> None:
    with pytest.raises(ValidationError):
        MultimodalSummaryProposal.model_validate({"modalities_present": [123]})


def test_valid_values_are_left_completely_untouched() -> None:
    """The tolerance path must not rewrite already-valid input."""
    payload = {
        "schema_version": "social-semiotic-preanalysis.v1",
        "summary": "unchanged",
        "modalities_present": ["visual", "linguistic"],
        "evidence": [
            {
                "evidence_id": "e1",
                "modality": "visual",
                "source_ref": "frame_0001.jpg",
                "frame_id": "f1",
                "exact_text": "text",
                "confidence": "high",
                "uncertainty": "",
            }
        ],
    }
    proposal = MultimodalSummaryProposal.model_validate(payload)
    assert proposal.summary == "unchanged"
    assert proposal.modalities_present == ["visual", "linguistic"]
    assert proposal.evidence[0].frame_id == "f1"
    assert proposal.evidence[0].source_ref == "frame_0001.jpg"
    assert proposal.model_dump(mode="json")["evidence"][0]["frame_id"] == "f1"


# ------------------------------------------- the boundary guard stays fail-closed


@pytest.mark.parametrize(
    "key",
    [
        "empty_signifiers",
        "nodal_points",
        "chains_of_equivalence",
        "antagonisms",
        "populism",
        "hegemony",
        "sentiment",
        "sentiment_observations",
    ],
)
def test_downstream_analytical_fields_are_still_rejected(key: str) -> None:
    """Key tolerance must not become a route around the pre-analysis boundary.

    These are not model fields, so they survive the tolerance pass and are then
    rejected by extra="forbid" — the guard is not bypassed by renaming.
    """
    with pytest.raises(ValidationError):
        MultimodalSummaryProposal.model_validate({"evidence": [], key: ["x"]})


def test_prohibited_key_near_a_real_field_name_is_not_renamed_into_it() -> None:
    """The safety property: a prohibited key must not be absorbed as a typo.

    'sentiment_observations' is a declared *property* on the proposal, not a field,
    and a downstream-only concept.  If the tolerance pass renamed it onto a real
    field it would smuggle a downstream classification into pre-analysis.
    """
    with pytest.raises(ValidationError):
        MultimodalSummaryProposal.model_validate({"sentiment_observations": ["angry"]})


def test_boundary_guard_still_fails_closed_on_a_dumped_proposal() -> None:
    """The guard that runs after validation remains effective on real output."""
    proposal = MultimodalSummaryProposal.model_validate(
        {"evidence": [{"evidence_id": "e1", "modality": "linguistic", "frame_id": None}]}
    )
    payload = proposal.model_dump(mode="json")
    assert_preanalysis_boundary(payload)
    payload["nodal_points"] = ["x"]
    with pytest.raises(ValueError, match="downstream analytical field"):
        assert_preanalysis_boundary(payload)


def test_word_populism_stays_allowed_as_evidence_not_classification() -> None:
    """Tolerance must not turn evidence about a concept into a classification of it."""
    proposal = MultimodalSummaryProposal.model_validate(
        {
            "summary": "The article discusses populism as a contested term.",
            "evidence": [
                {"evidence_id": "e1", "modality": "linguistic", "exact_text": "populism"}
            ],
        }
    )
    assert_preanalysis_boundary(proposal.model_dump(mode="json"))
    assert proposal.summary.startswith("The article discusses")
