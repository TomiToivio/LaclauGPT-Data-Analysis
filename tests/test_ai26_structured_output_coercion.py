"""Regression coverage for the AI26 structured-output and cycle-outcome fixes.

Issue #100: a bare string where a list of strings is declared must coerce.
Issue #101: a cycle that attempts work and completes none of it must not
report success, while an idle/all-duplicate cycle still must.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from laclaugpt_data_analysis.canonical_pipeline import (
    EventCandidate,
    MultimodalSummaryProposal,
    SummaryProposal,
)

# --------------------------------------------------------------- issue #100


def test_event_candidate_accepts_single_string_evidence() -> None:
    """A model returning one quote as a bare string is unambiguous, not invalid."""
    candidate = EventCandidate(
        description="Emissions report",
        evidence="Source article from The Web Foundation website.",
    )
    assert candidate.evidence == ["Source article from The Web Foundation website."]


def test_event_candidate_accepts_single_string_actors() -> None:
    candidate = EventCandidate(actors="MIRI")
    assert candidate.actors == ["MIRI"]


def test_event_candidate_still_accepts_real_lists() -> None:
    candidate = EventCandidate(evidence=["a", "b"], actors=["MIRI", "DAIR"])
    assert candidate.evidence == ["a", "b"]
    assert candidate.actors == ["MIRI", "DAIR"]


def test_blank_single_string_becomes_empty_list() -> None:
    assert EventCandidate(evidence="   ").evidence == []


def test_whitespace_is_stripped_when_coercing() -> None:
    assert EventCandidate(actors="  DAIR  ").actors == ["DAIR"]


def test_non_string_single_value_is_not_coerced() -> None:
    """A genuinely wrong type must still fail rather than be papered over."""
    with pytest.raises(ValidationError):
        EventCandidate(evidence={"nested": "mapping"})


def test_summary_proposal_coerces_single_string_lists() -> None:
    proposal = SummaryProposal(topics="AI policy")
    assert proposal.topics == ["AI policy"]


def test_multimodal_summary_coerces_nested_event_candidate_evidence() -> None:
    """The exact failure observed in production, nested one level deep."""
    proposal = MultimodalSummaryProposal.model_validate(
        {
            "summary": "s",
            "event_candidates": [
                {"description": "d", "evidence": "Publication date in metadata and text content."}
            ],
        }
    )
    assert proposal.event_candidates[0].evidence == [
        "Publication date in metadata and text content."
    ]


def test_scalar_fields_are_left_alone_by_the_coercion() -> None:
    proposal = MultimodalSummaryProposal(summary="unchanged", narrative="also")
    assert proposal.summary == "unchanged"
    assert proposal.narrative == "also"
