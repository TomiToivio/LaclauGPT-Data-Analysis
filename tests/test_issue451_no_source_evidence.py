"""#451: a record with no stored source text must abstain, not be interpreted.

The measured defect: 27 of 3,632 review items carried no source text and still
received a formation, signifiers and an antagonism. The model was answering from
the record's metadata. These tests pin the behaviour the pipeline now has:
nothing to read means no interpretation, a recorded reason, and no provider call.
"""
from __future__ import annotations

from datetime import UTC, datetime

from laclaugpt_data_analysis.canonical import CanonicalRecord, ContentSection, Transcript
from laclaugpt_data_analysis.stages.evidence_gate import (
    NO_SOURCE_EVIDENCE_REASON,
    abstain_without_source_evidence,
    source_evidence,
)
from laclaugpt_data_analysis.stages.postprocess import postprocess_record
from laclaugpt_data_analysis.stages.proposals import (
    DiscourseProposal,
    DiscursiveElement,
    DiscursiveRelation,
    MultimodalSummaryProposal,
)


def record(text: str = "", **content) -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.org/451",
        source={"platform": "mastodon", "created_at": datetime(2026, 11, 16, tzinfo=UTC)},
        content=ContentSection(text=text, **content),
    )


def rich_proposal() -> tuple[MultimodalSummaryProposal, DiscourseProposal]:
    """What a model returns when it answers anyway from title and handle."""
    summary = MultimodalSummaryProposal(summary="A confident summary.", topics=["AI governance"])
    discourse = DiscourseProposal(
        collective_subjects=[DiscursiveElement(label="the public")],
        formation_candidates=[DiscursiveElement(label="accelerationist")],
        floating_signifier_candidates=[DiscursiveElement(label="innovation")],
        nodal_point_candidates=[DiscursiveElement(label="safety")],
        antagonisms=[
            DiscursiveRelation(
                relation_type="antagonism", source="the public", target="Big Tech"
            )
        ],
    )
    return summary, discourse


def test_empty_text_abstains_and_writes_no_coded_fields():
    rec = record("")

    summary, discourse = rich_proposal()
    postprocess_record(rec, summary, discourse)

    assert rec.analysis.status == "no_evidence"
    assert rec.analysis.summary is None
    assert rec.analysis.formations == []
    assert rec.analysis.signifiers == []
    assert rec.analysis.antagonisms == []
    assert rec.analysis.topics == []
    assert rec.analysis.us == []
    assert NO_SOURCE_EVIDENCE_REASON in rec.analysis.abstentions


def test_abstention_is_recorded_as_a_stage_decision_not_a_log_line():
    rec = record("   \n\t ")
    postprocess_record(rec, *rich_proposal())

    gate = rec.intermediate.stage_outputs["evidence_gate"][-1]
    assert gate["decision"] == "abstain"
    assert gate["reason"] == "no_source_evidence"
    assert gate["chars"] == 0
    assert gate["policy"] == "evidence_first_v1"


def test_abstention_does_not_duplicate_notes_on_second_call():
    rec = record("")
    assert abstain_without_source_evidence(rec, stage="first") is True
    assert abstain_without_source_evidence(rec, stage="second") is True

    assert rec.analysis.abstentions.count(NO_SOURCE_EVIDENCE_REASON) == 1
    assert len(rec.intermediate.stage_outputs["evidence_gate"]) == 2


def test_source_text_still_analyses_normally():
    rec = record("The government must pause frontier model training immediately.")

    postprocess_record(rec, *rich_proposal())

    assert rec.analysis.status == "analyzed"
    assert rec.analysis.summary == "A confident summary."
    assert [item.label for item in rec.analysis.formations] == ["accelerationist"]
    assert rec.analysis.abstentions == []


def test_a_transcript_is_source_evidence_even_without_text():
    rec = record("", transcripts=[Transcript(id="t1", text="Spoken argument about AI risk.")])

    assert source_evidence(rec)["available"] is True
    assert source_evidence(rec)["modalities"]["transcripts"] > 0
    assert abstain_without_source_evidence(rec, stage="test") is False


def test_metadata_is_not_source_evidence():
    # A title and a link-card reference are pointers, not text a quote can be
    # located in; they must not satisfy the gate.
    rec = record("", title="AI datacentre announced", media_references=[])

    assert source_evidence(rec)["available"] is False


def test_canonical_runner_abstains_without_spending_a_model_call():
    from laclaugpt_data_analysis.llm.base import ChatRequest
    from laclaugpt_data_analysis.stages.runner import run_canonical_pipeline

    class CountingProvider:
        def __init__(self):
            self.requests = []

        def chat(self, request: ChatRequest):  # pragma: no cover - must not run
            self.requests.append(request)
            raise AssertionError("no model call may be made when there is no source text")

    provider = CountingProvider()
    result = run_canonical_pipeline(record(""), provider=provider, project_profile="ai26")

    assert provider.requests == []
    assert result.analysis.status == "no_evidence"
    assert result.analysis.summary is None
    assert NO_SOURCE_EVIDENCE_REASON in result.analysis.abstentions
    assert result.intermediate.stage_outputs["evidence_gate"][-1]["stage"] == "runner"
    assert result.intermediate.stage_outputs["pipeline_abstained"][-1]["reason"] == "no_source_evidence"
