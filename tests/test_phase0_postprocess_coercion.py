"""Regression coverage for issue #206 Phase 0 summary normalization."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from laclaugpt_postprocess import validate_summary


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


def test_non_string_invalid_container_still_fails() -> None:
    with pytest.raises(ValidationError):
        validate_summary(
            _record(),
            {
                "summary": "Usable summary.",
                "evidence": {"quote": "not a list"},
            },
        )
