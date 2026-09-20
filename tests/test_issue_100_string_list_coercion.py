from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from laclaugpt_data_analysis.canonical_pipeline import MultimodalSummaryProposal
from laclaugpt_data_analysis.llm.structured_output import parse_structured
from laclaugpt_data_analysis.social_semiotic import UncertaintyObservation


def test_single_string_list_fields_are_coerced_without_retry_shape_failure() -> None:
    payload = {
        "summary": "Synthetic summary",
        "semiotic_modes": "speech",
        "topics": "AI policy",
        "event_candidates": [
            {
                "description": "A hearing is announced.",
                "actors": "Example Ministry",
                "evidence": "Source article states that the hearing was announced.",
                "confidence": 0.8,
            }
        ],
        "limitations": "No audio was supplied.",
    }

    parsed = parse_structured(json.dumps(payload), MultimodalSummaryProposal)

    assert parsed.semiotic_modes == ["speech"]
    assert parsed.topics == ["AI policy"]
    assert parsed.event_candidates[0].actors == ["Example Ministry"]
    assert parsed.event_candidates[0].evidence == [
        "Source article states that the hearing was announced."
    ]
    assert parsed.limitations == ["No audio was supplied."]


def test_empty_scalar_string_becomes_empty_list() -> None:
    parsed = parse_structured(
        json.dumps({"summary": "Synthetic summary", "topics": "   "}),
        MultimodalSummaryProposal,
    )
    assert parsed.topics == []


def test_typed_uncertainty_remains_explicit() -> None:
    parsed = MultimodalSummaryProposal(
        uncertainty=[
            UncertaintyObservation(
                category="source_context",
                description="Event date is not stated.",
                confidence="low",
            )
        ]
    )
    assert parsed.uncertainty[0].description == "Event date is not stated."


def test_non_string_wrong_shape_remains_strict() -> None:
    payload = {
        "summary": "Synthetic summary",
        "event_candidates": [
            {
                "description": "A hearing is announced.",
                "evidence": {"quote": "This must not be silently accepted."},
            }
        ],
    }

    with pytest.raises(ValidationError):
        parse_structured(json.dumps(payload), MultimodalSummaryProposal)
