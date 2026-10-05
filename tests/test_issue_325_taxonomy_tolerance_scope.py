"""#325: the #299 taxonomy tolerance must be a property of the contract, not the base class.

The near-miss tolerance in :mod:`laclaugpt_data_analysis.social_semiotic` used to
live only on ``StrictMethodModel``. ``CriticalAIAnalysis`` and the DNA statement
schemas inherit plain ``BaseModel``, so they hard-failed on the same reversible
spelling drift the pre-analysis schema already canonicalises. These tests pin
the shared behaviour and, just as importantly, pin that strictness is intact.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from laclaugpt_data_analysis.critical_ai import (
    CriticalAIAnalysis,
    CriticalAIFinding,
    CriticalAIObject,
)
from laclaugpt_data_analysis.dna_statement_coding import (
    DNAStatementBatch,
    DNAStatementCandidate,
)
from laclaugpt_data_analysis.social_semiotic import (
    CompositionObservation,
    StrictMethodModel,
    TaxonomyToleranceMixin,
)


def test_critical_ai_normalises_unambiguous_spelling_drift() -> None:
    analysis = CriticalAIAnalysis.model_validate(
        {"ai_object": {"types": ["organization", "labor_process"]}}
    )

    assert analysis.ai_object.types == ["organisation", "labour_process"]


def test_critical_ai_normalises_drift_in_nested_finding_fields() -> None:
    finding = CriticalAIFinding.model_validate(
        {
            "dimension": "labour",
            "claim": "Synthetic claim.",
            "scope": "organization",
            "review": {"status": "provisionel"},
        }
    )

    assert finding.scope == "organisation"
    assert finding.review.status == "provisional"


def test_critical_ai_scope_tolerance_is_reachable_through_the_root_model() -> None:
    analysis = CriticalAIAnalysis.model_validate(
        {
            "ai_object": {"types": ["organization"]},
            "findings": [
                {"dimension": "labour", "claim": "Synthetic claim.", "scope": "organization"}
            ],
        }
    )

    assert analysis.findings[0].scope == "organisation"


def test_dna_statement_normalises_drift_in_nested_literals() -> None:
    candidate = DNAStatementCandidate.model_validate(
        {
            "concept": {"label": "synthetic-concept"},
            "organization": {"label": "Synthetic Institute"},
            "evidence_text": "Synthetic evidence.",
            "agreement_status": "not applicable",
        }
    )

    assert candidate.agreement_status == "not_applicable"

    batch = DNAStatementBatch.model_validate(
        {
            "statements": [
                {
                    "concept": {"label": "synthetic-concept"},
                    "organization": {"label": "Synthetic Institute"},
                    "evidence_text": "Synthetic evidence.",
                    "agreement_status": "not applicable",
                }
            ]
        }
    )

    assert batch.statements[0].agreement_status == "not_applicable"


def test_critical_ai_still_rejects_genuinely_distant_values() -> None:
    for distant in ("algorithm", "not_applicable", "institution", "system"):
        with pytest.raises(ValidationError):
            CriticalAIAnalysis.model_validate({"ai_object": {"types": [distant]}})


def test_critical_ai_keeps_required_fields_and_types_strict() -> None:
    with pytest.raises(ValidationError):
        CriticalAIFinding.model_validate({"claim": "Synthetic claim."})

    with pytest.raises(ValidationError):
        CriticalAIObject.model_validate({"types": "organization"})


def test_dna_actor_and_agreement_invariants_are_unchanged() -> None:
    with pytest.raises(ValidationError, match="person or organization speaker"):
        DNAStatementCandidate.model_validate(
            {
                "concept": {"label": "synthetic-concept"},
                "evidence_text": "Synthetic evidence.",
            }
        )

    with pytest.raises(ValidationError, match="coded agreement requires true or false"):
        DNAStatementCandidate.model_validate(
            {
                "concept": {"label": "synthetic-concept"},
                "person": {"label": "Synthetic Speaker"},
                "evidence_text": "Synthetic evidence.",
                "agreement_status": "coded",
            }
        )


def test_tolerance_is_shared_across_both_families_but_extra_policy_is_local() -> None:
    """Tolerance is shared; the ``extra`` policy still belongs to each model.

    ``StrictMethodModel`` forbids unknown fields; the Critical AI / DNA models
    keep pydantic's default (ignore). The mixin must not change that split.
    """

    assert issubclass(StrictMethodModel, TaxonomyToleranceMixin)
    assert issubclass(CriticalAIObject, TaxonomyToleranceMixin)

    with pytest.raises(ValidationError):
        CompositionObservation.model_validate(
            {"feature": "layout", "description": "d", "unexpected": True}
        )

    # The Critical AI family keeps ignoring unknowns, exactly as before #325.
    assert CriticalAIObject.model_validate({"types": [], "unexpected": True}).types == []
