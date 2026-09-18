from __future__ import annotations

from laclaugpt_data_analysis.canonical import CanonicalRecord, ContentSection, SourceSection
from laclaugpt_data_analysis.canonical_pipeline import (
    DiscourseProposal,
    MultimodalSummaryProposal,
    PipelineContext,
    _effective_stage_set,
    _validate_project_analysis_config,
    postprocess_record,
)


def _record() -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.test/item",
        source=SourceSection(platform="test"),
        content=ContentSection(text="AI policy debate"),
    )


def test_enabled_summary_capabilities_are_projected() -> None:
    record = _record()
    summary = MultimodalSummaryProposal(
        summary="summary",
        topics=["AI regulation"],
        entities=["European Union"],
        sentiment_observations=["critical concern"],
    )
    ctx = PipelineContext(
        project_config={
            "analysis": {
                "laclau": True,
                "sociotechnical_imaginaries": True,
                "topics": True,
                "entities": True,
                "sentiment": True,
                "sna": False,
                "ant": False,
                "valueflows": False,
            }
        }
    )

    postprocess_record(record, summary, DiscourseProposal(), ctx)

    assert [item.canonical_label for item in record.analysis.topics] == ["AI regulation"]
    assert [item.label for item in record.analysis.entities] == ["European Union"]
    assert [item.label for item in record.analysis.sentiments] == ["critical concern"]


def test_disabled_summary_capability_stays_empty() -> None:
    record = _record()
    summary = MultimodalSummaryProposal(topics=["AI regulation"])
    ctx = PipelineContext(project_config={"analysis": {"topics": False}})
    postprocess_record(record, summary, DiscourseProposal(), ctx)
    assert record.analysis.topics == []


def test_phase2_capability_can_be_explicitly_selected_without_entering_default_stage_set() -> None:
    ctx = PipelineContext(project_config={"analysis": {"sna": True}})
    _validate_project_analysis_config(ctx)
    assert "sna" in _effective_stage_set(ctx)


def test_effective_stage_set_is_auditable() -> None:
    ctx = PipelineContext(
        project_config={
            "analysis": {
                "laclau": True,
                "topics": True,
                "entities": False,
                "sentiment": True,
                "dna_statement_coding": {"enabled": False},
                "critical_ai": {"enabled": False},
            }
        }
    )
    assert _effective_stage_set(ctx) == ["laclau", "sentiment", "topics"]
