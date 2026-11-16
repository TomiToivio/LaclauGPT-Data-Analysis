"""#452: Phase 1 codes collective subjects, not a us/them pair.

`us` was written from `discourse.collective_subjects` and `them` was written
nowhere, while `research_record.py`, `rdf.py` and `knowledge_graph.py` all
exported the pair. A consumer saw one pole of an antagonistic relation and no
way to know the other was never coded.

The ruling applied here is codebook-derived: `phase1_v1.yaml` declares
`collective_subjects` and no `them`, and the opposed pole, where the source
states one, is already an `antagonism` with a `target_ref`.
"""
from __future__ import annotations

from datetime import UTC, datetime

from laclaugpt_data_analysis.canonical import CanonicalRecord, ContentSection, DiscourseObject
from laclaugpt_data_analysis.research_record import ensure_research_layers, legacy_projection
from laclaugpt_data_analysis.stage_contract import STAGE_CAPABILITIES
from laclaugpt_data_analysis.stages.postprocess import postprocess_record
from laclaugpt_data_analysis.stages.proposals import (
    DiscourseProposal,
    DiscursiveElement,
    MultimodalSummaryProposal,
)


def record(text: str = "The government must regulate frontier models now.") -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.org/452",
        source={"platform": "news", "created_at": datetime(2026, 11, 16, tzinfo=UTC)},
        content=ContentSection(text=text),
    )


def proposal() -> DiscourseProposal:
    return DiscourseProposal(
        collective_subjects=[DiscursiveElement(label="civil society")],
        formation_candidates=[DiscursiveElement(label="ai_safety")],
    )


def test_postprocess_writes_collective_subjects_and_no_pair():
    rec = record()
    postprocess_record(rec, MultimodalSummaryProposal(summary="S"), proposal())

    assert [item.label for item in rec.analysis.collective_subjects] == ["civil society"]
    assert rec.analysis.us == []
    assert rec.analysis.them == []


def test_legacy_us_is_lifted_to_the_codebook_field_on_load():
    rec = record()
    rec.analysis.us = [DiscourseObject(object_id="us:1", label="the builders", kind="collective_subject")]

    ensure_research_layers(rec)

    assert [item.label for item in rec.analysis.collective_subjects] == ["the builders"]


def test_projection_exports_collective_subjects_and_keeps_us_as_an_alias():
    rec = record()
    postprocess_record(rec, MultimodalSummaryProposal(summary="S"), proposal())

    projection = legacy_projection(rec)

    assert projection["collective_subjects"] == "civil society"
    # The legacy column keeps its data under its old name so existing readers do
    # not silently lose rows; it is now a documented alias, not a second construct.
    assert projection["us"] == "civil society"
    # The EP24-era wide frame keeps an empty `them` column so old researcher
    # dataframes keep their shape, but it is never derived from the analysis.
    assert projection["them"] == ""
    assert "collective_subjects" in projection


def test_stage_contract_declares_the_field_the_stage_actually_produces():
    laclau = STAGE_CAPABILITIES["laclau"]
    palonen = STAGE_CAPABILITIES["palonen"]

    assert "collective_subjects" in laclau.output_fields
    assert "us" not in laclau.output_fields
    assert "collective_subjects" in palonen.output_fields
