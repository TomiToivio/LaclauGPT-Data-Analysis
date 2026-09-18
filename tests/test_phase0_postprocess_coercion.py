"""Regression coverage for issue #206 Phase 0 summary normalization."""
from __future__ import annotations

import pytest
from laclaugpt_postprocess import validate_summary
from pydantic import ValidationError


def _record() -> dict:
    return {
        "document_id": "doc-1",
        "source_url": "https://example.org/doc-1",
        "metadata": {},
    }


def test_scalar_list_fields_are_normalized_and_recorded() -> None:
    summary = {
        "summary": "Usable summary.",
        "future_visions": "Superhuman AI could cause catastrophic outcomes.",
        "governance_positions": "Pause frontier model development.",
        "evidence": "The document explicitly calls for a pause.",
        "uncertainty_notes": "Model confidence is limited.",
    }

    validated = validate_summary(_record(), summary)

    assert validated.future_visions == [
        "Superhuman AI could cause catastrophic outcomes."
    ]
    assert validated.governance_positions == ["Pause frontier model development."]
    assert validated.evidence == ["The document explicitly calls for a pause."]
    assert validated.uncertainty_notes[0] == "Model confidence is limited."
    assert "future_visions" in validated.uncertainty_notes[-1]
    assert "governance_positions" in validated.uncertainty_notes[-1]
    assert "evidence" in validated.uncertainty_notes[-1]
    assert "uncertainty_notes" in validated.uncertainty_notes[-1]


def test_existing_lists_are_preserved_without_normalization_note() -> None:
    summary = {
        "summary": "Usable summary.",
        "future_visions": ["One", "Two"],
        "uncertainty_notes": ["Original note"],
    }

    validated = validate_summary(_record(), summary)

    assert validated.future_visions == ["One", "Two"]
    assert validated.uncertainty_notes == ["Original note"]


def test_blank_scalar_list_field_becomes_empty_list() -> None:
    validated = validate_summary(
        _record(),
        {
            "summary": "Usable summary.",
            "evidence": "   ",
        },
    )

    assert validated.evidence == []
    assert "evidence" in validated.uncertainty_notes[-1]


def test_null_list_field_becomes_empty_list_and_is_recorded() -> None:
    validated = validate_summary(
        _record(),
        {
            "summary": "Usable summary.",
            "governance_positions": None,
        },
    )

    assert validated.governance_positions == []
    assert "governance_positions" in validated.uncertainty_notes[-1]


def test_non_string_invalid_container_still_fails() -> None:
    with pytest.raises(ValidationError):
        validate_summary(
            _record(),
            {
                "summary": "Usable summary.",
                "evidence": {"quote": "not a list"},
            },
        )


# --------------------------------------------------------------------------
# issue #233: an explicit null is not the same as an absent key
# --------------------------------------------------------------------------

def test_null_in_several_fields_is_normalized_together() -> None:
    validated = validate_summary(
        _record(),
        {
            "summary": "Usable summary.",
            "future_visions": None,
            "evidence": None,
            "uncertainty_notes": None,
        },
    )

    assert validated.future_visions == []
    assert validated.evidence == []
    # uncertainty_notes becomes empty and then carries the normalization note, exactly as
    # a blank uncertainty_notes string already did.
    note = validated.uncertainty_notes[-1]
    assert "future_visions" in note
    assert "evidence" in note
    assert "uncertainty_notes" in note


def test_absent_key_is_not_reported_as_a_normalization() -> None:
    """A field the model never returned keeps its default and is not coerced.

    This is the distinction #233 is about: absence is not a normalization event, so
    provenance should not claim the field was rewritten.
    """
    validated = validate_summary(_record(), {"summary": "Usable summary."})

    assert validated.governance_positions == []
    assert not any(
        "normalized scalar list field" in str(note) for note in validated.uncertainty_notes
    )


def test_null_and_scalar_are_normalized_together_and_both_recorded() -> None:
    validated = validate_summary(
        _record(),
        {
            "summary": "Usable summary.",
            "evidence": None,
            "governance_positions": "Pause frontier model development.",
        },
    )

    assert validated.evidence == []
    assert validated.governance_positions == ["Pause frontier model development."]
    note = validated.uncertainty_notes[-1]
    assert "evidence" in note
    assert "governance_positions" in note


def test_null_does_not_mask_a_genuinely_wrong_container() -> None:
    """Coercing null must not make validation lax overall."""
    with pytest.raises(ValidationError):
        validate_summary(
            _record(),
            {
                "summary": "Usable summary.",
                "governance_positions": None,
                "evidence": ["fine"],
                "claims": 42,
            },
        )
