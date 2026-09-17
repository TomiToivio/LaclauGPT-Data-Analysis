from datetime import UTC, date, datetime

from laclaugpt_data_analysis.canonical import CanonicalRecord, DiscourseObject
from laclaugpt_data_analysis.canonical_pipeline import (
    DiscourseProposal,
    DiscursiveElement,
    DiscursiveRelation,
    MultimodalSummaryProposal,
    PipelineContext,
    build_discourse_graph,
    postprocess_record,
    run_canonical_pipeline,
)
from laclaugpt_data_analysis.context_envelope import build_prompt_envelope
from laclaugpt_data_analysis.distributed import ProjectNamespace
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.reporting import build_daily_report


class SequencedProvider:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.requests.append(request)
        payload = self.payloads.pop(0)
        return LLMResponse(
            content=payload.model_dump_json(),
            provenance=LLMCallProvenance(
                requested_mode="local",
                requested_model="fake-model",
                resolved_model="fake-model",
                actual_mode="local",
                actual_model="fake-model",
                endpoint="fake",
            ),
        )


def synthetic_record() -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/item/1",
        raw_capture={"payload": {"unknown_collector_field": "must survive"}},
        source={
            "platform": "synthetic",
            "author": "Researcher Example",
            "created_at": datetime(2026, 9, 16, 8, 0, tzinfo=UTC),
            "raw_metadata": {"collector_native": 42},
        },
        content={"title": "Synthetic AI debate", "text": "AI should serve democratic society."},
        legacy={"whisperResult": "legacy transcript", "frame_analysis_1": "legacy visual note"},
    )


def test_prompt_envelope_has_all_eight_sections_and_empty_fallbacks():
    record = synthetic_record()
    envelope = build_prompt_envelope(record, task="Do the current stage", project_context="AI26")
    rendered = envelope.render()
    for section in (
        "PROJECT CONTEXT",
        "SOURCE CONTEXT",
        "SITUATIONAL CONTEXT",
        "CONTEXT MEMORY",
        "RAG CONTEXT",
        "CURRENT SOURCE ITEM",
        "PREVIOUS ANALYSIS",
        "TASK",
    ):
        assert f"[{section}]" in rendered
    assert "(none available)" in rendered
    assert "unknown_collector_field" in rendered


def test_pipeline_keeps_raw_legacy_human_and_structured_layers():
    summary = MultimodalSummaryProposal(
        summary="Human-readable synthetic summary",
        narrative="A synthetic debate about democratic control of AI.",
        topics=["AI governance"],
        entities=["Synthetic Lab"],
        later_analysis_cues=["Later discourse analysis may examine democratic AI claims."],
    )
    discourse = DiscourseProposal(
        demands=[
            DiscursiveElement(
                label="democratic control",
                evidence=["AI should serve democratic society."],
                confidence=0.8,
            )
        ],
        nodal_point_candidates=[
            DiscursiveElement(
                label="AI",
                evidence=["AI should serve democratic society."],
                confidence=0.7,
            )
        ],
        formation_candidates=[
            DiscursiveElement(
                label="democratic AI project",
                evidence=["AI should serve democratic society."],
                confidence=0.4,
            )
        ],
        imaginary_candidates=[
            DiscursiveElement(
                label="democratically governed AI",
                evidence=["AI should serve democratic society."],
                confidence=0.4,
            )
        ],
        populist=False,
        non_populist_reason="No constitutive Us/Frontier pair is evidenced.",
        abstentions=["No empty signifier finding at document level."],
    )
    provider = SequencedProvider([summary, discourse])
    record = synthetic_record()
    result = run_canonical_pipeline(
        record,
        provider=provider,
        context=PipelineContext(
            project_context="AI26 public methodological profile",
            source_context="Synthetic source codebook entry",
            situational_context="Latest daily summary",
            memory_context="Canonical signifier: AI",
            rag_context="Retrieved context, not evidence",
        ),
        model="fake-model",
        project_profile="ai26",
    )

    assert result.raw_capture.payload["unknown_collector_field"] == "must survive"
    assert result.source.raw_metadata["collector_native"] == 42
    assert result.legacy["whisperResult"] == "legacy transcript"
    assert result.human_readable.summary == "Human-readable synthetic summary"
    assert result.analysis.entities[0].label == "Synthetic Lab"
    assert result.analysis.formations[0].review_status == "PROVISIONAL"
    assert result.analysis.formations[0].metadata["corpus_validation_required"] is True
    assert result.analysis.formula_of_populism["populist"] is False
    assert "multimodal_synthesis" in result.intermediate.stage_outputs
    assert "castells_context" in result.intermediate.stage_outputs
    assert "discourse_analysis" in result.intermediate.stage_outputs
    assert "discourse_graph" in result.intermediate.stage_outputs
    assert len(provider.requests) == 2
    for request in provider.requests:
        assert "[PROJECT CONTEXT]" in request.user
        assert "[RAG CONTEXT]" in request.user
        assert "[PREVIOUS ANALYSIS]" in request.user
        assert "[TASK]" in request.user


def test_postprocess_projects_typed_laclau_fields_without_dropping_generic_views():
    record = synthetic_record()
    summary = MultimodalSummaryProposal(
        summary="Synthetic summary",
        entities=["Synthetic Lab"],
        sentiment_observations=["cautiously optimistic"],
    )
    discourse = DiscourseProposal(
        floating_signifier_candidates=[
            DiscursiveElement(
                label="progress",
                evidence=["Progress means AI that serves democratic society."],
                confidence=0.6,
            )
        ],
        empty_signifier_candidates=[
            DiscursiveElement(
                label="democracy",
                evidence=["Democracy can unite otherwise distinct demands."],
                confidence=0.5,
            )
        ],
        equivalences=[
            DiscursiveRelation(
                relation_type="equivalence",
                source="democracy",
                target="public control",
                evidence=["Democracy and public control are articulated together."],
            )
        ],
        differences=[
            DiscursiveRelation(
                relation_type="difference",
                source="public control",
                target="private ownership",
                evidence=["Public control is distinguished from private ownership."],
            )
        ],
        antagonisms=[
            DiscursiveRelation(
                relation_type="antagonism",
                source="democratic public",
                target="unaccountable monopoly",
                evidence=["An unaccountable monopoly blocks democratic control."],
            )
        ],
    )

    result = postprocess_record(record, summary, discourse)

    assert [item.label for item in result.analysis.floating_signifiers] == ["progress"]
    assert [item.label for item in result.analysis.empty_signifier_candidates] == ["democracy"]
    assert {item.label for item in result.analysis.signifiers} == {"progress", "democracy"}
    assert result.analysis.equivalence_chains[0].member_refs == ["democracy", "public control"]
    assert result.analysis.difference_chains[0].member_refs == ["public control", "private ownership"]
    assert result.analysis.antagonisms[0].target_ref == "unaccountable monopoly"
    assert any(item.relation_type == "equivalence" for item in result.analysis.relations)
    assert any(item.relation_type == "difference" for item in result.analysis.relations)
    assert any(item.relation_type == "antagonism" for item in result.analysis.relations)
    assert result.analysis.sentiments[0].label == "cautiously optimistic"


def test_graph_is_projection_not_second_ontology():
    record = synthetic_record()
    record.analysis.signifiers = [
        DiscourseObject(
            object_id="signifier:1",
            label="AI",
            kind="signifier",
            review_status="PROVISIONAL",
        )
    ]
    graph = build_discourse_graph(record)
    assert graph["source_url"] == record.source_url
    assert any(node["id"] == "signifier:1" for node in graph["nodes"])
    assert any(edge["type"] == "CANDIDATE_IN" for edge in graph["edges"])


def test_daily_reports_can_filter_by_signifier_and_feed_context():
    record = synthetic_record()
    record.analysis.signifiers = [
        DiscourseObject(
            object_id="signifier:1",
            label="AI",
            kind="signifier",
            review_status="PROVISIONAL",
        )
    ]
    record.human_readable.summary = "Synthetic daily summary"
    report = build_daily_report(
        [record], report_date=date(2026, 9, 16), filters={"signifier": "AI"}
    )
    assert report.record_count == 1
    assert report.top_signifiers == ["AI"]
    assert "do not by themselves establish" in report.markdown.lower()
    assert "Synthetic daily summary" in report.markdown


def test_distributed_namespace_supports_three_pipeline_collections():
    namespace = ProjectNamespace("ai26")
    assert namespace.mongo_collection("raw") == "ai26__raw"
    assert namespace.mongo_collection("processing") == "ai26__processing"
    assert namespace.mongo_collection("analyzed") == "ai26__analyzed"
