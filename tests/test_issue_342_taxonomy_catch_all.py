"""#342: a value the taxonomy does not have becomes its declared ``other``, audibly.

The live AI26 queue showed the model proposing kinds the closed vocabularies do not
list - ``methodology`` in ``ai_object.types``, ``not_applicable`` in a finding's
``dimension``, and a family of relation/process kinds. Each cost two validation
attempts and a retry. These tests pin the fix and, just as importantly, pin that
everything outside the declared policy table stays strict.
"""
from __future__ import annotations

import typing

import pytest
from pydantic import ValidationError

from laclaugpt_data_analysis import critical_ai, social_semiotic
from laclaugpt_data_analysis.critical_ai import (
    CriticalAIAnalysis,
    CriticalAIFinding,
    CriticalAIObject,
)
from laclaugpt_data_analysis.social_semiotic import (
    CompositionObservation,
    IntermodalRelation,
    MultimodalSummaryProposal,
    ProcessObservation,
    SemioticResource,
    SignRelation,
    TaxonomyToleranceMixin,
    UncertaintyObservation,
    _TAXONOMY_CATCH_ALL_FIELDS,
    drain_taxonomy_substitutions,
    taxonomy_catch_all_fields,
)

#: Values seen in the live Laskin analysis log, each with the field it broke and the
#: companions that model requires. ``recorded`` is the string the vocabulary lacked.
CASES = [
    pytest.param(
        CriticalAIObject, "types", ["methodology"], {}, ["other"], "methodology",
        id="types-methodology",
    ),
    pytest.param(
        CriticalAIFinding, "dimension", "not_applicable", {"claim": "Synthetic claim."},
        "other", "not_applicable", id="dimension-not_applicable",
    ),
    pytest.param(
        CompositionObservation, "feature", "headline", {"description": "Synthetic."},
        "other", "headline", id="feature-headline",
    ),
    pytest.param(
        SignRelation, "relation_type", "comparison",
        {"source_sign_ref": "sign-1", "target_sign_ref": "sign-2"},
        "other", "comparison", id="sign-relation-comparison",
    ),
    pytest.param(
        IntermodalRelation, "relation_type", "layering",
        {"modes": ["linguistic"], "description": "Synthetic."},
        "other", "layering", id="intermodal-relation-layering",
    ),
    pytest.param(
        ProcessObservation, "process_type", "condition",
        {"process_id": "process-1", "description": "Synthetic."},
        "other", "condition", id="process-condition",
    ),
    pytest.param(
        UncertaintyObservation, "category", "context", {"description": "Synthetic."},
        "other", "context", id="uncertainty-context",
    ),
]


@pytest.fixture(autouse=True)
def _clear_ledger():
    drain_taxonomy_substitutions()
    yield
    drain_taxonomy_substitutions()


@pytest.mark.parametrize("model, field, value, extra, expected, recorded", CASES)
def test_an_observed_offender_becomes_the_taxonomy_catch_all(
    model, field, value, extra, expected, recorded
) -> None:
    instance = model.model_validate({field: value, **extra})
    assert getattr(instance, field) == expected


@pytest.mark.parametrize("model, field, value, extra, expected, recorded", CASES)
def test_the_original_value_is_recorded_not_discarded(
    model, field, value, extra, expected, recorded
) -> None:
    model.model_validate({field: value, **extra})
    ledger = drain_taxonomy_substitutions()
    assert ledger, "the substitution must leave a trace"
    assert ledger[0] == {"model": model.__name__, "field": field, "value": recorded}


def test_the_policy_table_is_the_only_thing_that_enables_the_catch_all() -> None:
    """A field opts in by being declared; nothing opts in by accident."""
    assert taxonomy_catch_all_fields("NotAModel") == frozenset()
    assert taxonomy_catch_all_fields("CriticalAIObject") == frozenset({"types"})
    for name, fields in _TAXONOMY_CATCH_ALL_FIELDS.items():
        assert fields, f"{name} declares an empty policy"


def test_every_declared_field_exists_and_declares_a_catch_all_member() -> None:
    """The table may not drift from the models it names."""
    for model_name, field_names in _TAXONOMY_CATCH_ALL_FIELDS.items():
        model = getattr(social_semiotic, model_name, None) or getattr(critical_ai, model_name, None)
        assert model is not None, f"{model_name} does not exist"
        assert issubclass(model, TaxonomyToleranceMixin)
        for field_name in field_names:
            assert field_name in model.model_fields, f"{model_name}.{field_name} does not exist"
            annotation = model.model_fields[field_name].annotation
            args = typing.get_args(annotation)
            if args and typing.get_origin(args[0]) is typing.Literal:
                members = typing.get_args(args[0])
            else:
                members = typing.get_args(annotation)
            assert "other" in members, f"{model_name}.{field_name} has no catch-all member"


def test_the_mode_taxonomy_stays_strict() -> None:
    """A miss there means the model misread the field, not that a kind is missing."""
    with pytest.raises(ValidationError):
        MultimodalSummaryProposal.model_validate({"modalities_present": ["zoological"]})
    with pytest.raises(ValidationError):
        SemioticResource.model_validate({"mode": "zoological", "description": "x"})


def test_statuses_scopes_and_confidences_stay_strict() -> None:
    with pytest.raises(ValidationError):
        CriticalAIFinding.model_validate(
            {"dimension": "labour", "claim": "x", "status": "probably_true"}
        )
    with pytest.raises(ValidationError):
        CriticalAIFinding.model_validate(
            {"dimension": "labour", "claim": "x", "scope": "planetary"}
        )
    with pytest.raises(ValidationError):
        SignRelation.model_validate(
            {
                "relation_type": "label",
                "source_sign_ref": "sign-1",
                "target_sign_ref": "sign-2",
                "confidence": "certain",
            }
        )


def test_near_miss_normalisation_still_wins_over_the_catch_all() -> None:
    """The catch-all must not swallow a value that is one step from a real member."""
    instance = CriticalAIObject.model_validate({"types": ["organization", "labor_process"]})
    assert instance.types == ["organisation", "labour_process"]
    assert drain_taxonomy_substitutions() == []


def test_the_root_analysis_model_reaches_the_policy_through_nesting() -> None:
    analysis = CriticalAIAnalysis.model_validate(
        {
            "ai_object": {"types": ["methodology"]},
            "findings": [{"dimension": "not_applicable", "claim": "Synthetic claim."}],
        }
    )
    assert analysis.ai_object.types == ["other"]
    assert analysis.findings[0].dimension == "other"
    recorded = {(item["field"], item["value"]) for item in drain_taxonomy_substitutions()}
    assert ("types", "methodology") in recorded
    assert ("dimension", "not_applicable") in recorded


def test_unlisted_values_inside_opted_in_fields_of_lists_are_handled() -> None:
    instance = CriticalAIObject.model_validate({"types": ["model", "methodology", "dataset"]})
    assert instance.types == ["model", "other", "dataset"]
    assert len(drain_taxonomy_substitutions()) == 1
