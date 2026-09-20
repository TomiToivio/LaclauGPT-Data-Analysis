from laclaugpt_data_analysis.canonical_pipeline import (
    DiscourseProposal,
    DiscursiveElement,
    MultimodalFrameProposal,
    MultimodalSummaryProposal,
)
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.phase1_handoff import HANDOFF_SCHEMA, visualization_handoff
from laclaugpt_data_analysis.phase1_runtime import (
    Phase1TextConfig,
    persist_phase1_record,
    run_phase1_text_record,
)


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


def phase0_document():
    return {
        "_id": "mongo-id",
        "source_url": "https://example.org/phase1",
        "document_id": "doc-1",
        "normalized_text": "AI should serve democratic society.",
        "phase0_summary": {"summary": "Stable Phase 0 baseline."},
        "phase0_discourse": {"nodal_points": ["legacy"]},
        "phase0": {"summary": {"status": "ok"}, "discourse": {"status": "ok"}},
    }


def test_phase1_defaults_off_and_makes_zero_provider_calls():
    provider = SequencedProvider([])
    record = run_phase1_text_record(phase0_document(), provider=provider)

    assert provider.requests == []
    assert record.analysis.summary == "Stable Phase 0 baseline."
    assert record.legacy["phase0"]["phase0_discourse"]["nodal_points"] == ["legacy"]


def test_phase1_text_summary_is_one_call_and_preserves_phase0():
    summary = MultimodalSummaryProposal(
        summary="Phase 1 summary.",
        narrative="A democratic AI claim.",
        claims=["AI should serve democratic society."],
        topics=["AI governance"],
    )
    provider = SequencedProvider([summary])
    record = run_phase1_text_record(
        phase0_document(),
        provider=provider,
        config=Phase1TextConfig(enabled=True, discourse_enabled=False, model="fake-model"),
    )

    assert len(provider.requests) == 1
    assert record.analysis.summary == "Phase 1 summary."
    assert record.analysis.status == "phase1-summary-only"
    assert record.content.frames == []
    assert record.legacy["phase0"]["phase0_summary"]["summary"] == "Stable Phase 0 baseline."
    assert "multimodal_synthesis" in record.intermediate.stage_outputs
    assert "discourse_analysis" not in record.intermediate.stage_outputs


def test_phase1_discourse_is_second_call_and_evidence_links_to_source():
    summary = MultimodalSummaryProposal(summary="Phase 1 summary.")
    discourse = DiscourseProposal(
        demands=[
            DiscursiveElement(
                label="democratic service",
                evidence=["AI should serve democratic society."],
                confidence=0.8,
            )
        ],
        nodal_point_candidates=[
            DiscursiveElement(
                label="AI",
                evidence=["AI should serve democratic society."],
                confidence=0.8,
            )
        ],
    )
    provider = SequencedProvider([summary, discourse])
    record = run_phase1_text_record(
        phase0_document(),
        provider=provider,
        config=Phase1TextConfig(enabled=True, discourse_enabled=True, model="fake-model"),
    )

    assert len(provider.requests) == 2
    assert record.analysis.status == "analyzed"
    assert "discourse_analysis" in record.intermediate.stage_outputs
    assert record.evidence
    assert record.evidence[0].source_url == record.source_url
    assert record.evidence[0].metadata["exact"] is True
    assert all(run["stage"] not in {"critical_ai", "dna_statement_coding"} for run in record.analysis.model_runs)


class FakeCollection:
    def __init__(self):
        self.calls = []

    def update_one(self, identity, update, upsert=False):
        self.calls.append((identity, update, upsert))
        return {"ok": 1}


def test_phase1_persistence_is_namespaced_and_never_overwrites_phase0():
    summary = MultimodalSummaryProposal(summary="Phase 1 summary.")
    provider = SequencedProvider([summary])
    source = phase0_document()
    record = run_phase1_text_record(
        source,
        provider=provider,
        config=Phase1TextConfig(enabled=True, discourse_enabled=False, model="fake-model"),
    )
    collection = FakeCollection()

    persist_phase1_record(collection, source, record)
    persist_phase1_record(collection, source, record)

    assert len(collection.calls) == 2
    identity, update, upsert = collection.calls[0]
    assert identity == {"_id": "mongo-id"}
    assert set(update["$set"]) == {"phase1"}
    assert update["$set"]["phase1"]["schema_version"] == record.schema_version
    assert update["$set"]["phase1"]["canonical_record"]["legacy"]["phase0"]["phase0_summary"]["summary"] == "Stable Phase 0 baseline."
    assert upsert is False


def test_visualization_handoff_excludes_phase0_private_namespaces():
    summary = MultimodalSummaryProposal(summary="Phase 1 summary.")
    provider = SequencedProvider([summary])
    record = run_phase1_text_record(
        phase0_document(),
        provider=provider,
        config=Phase1TextConfig(enabled=True, discourse_enabled=False, model="fake-model"),
    )
    handoff = visualization_handoff(record)

    assert handoff["handoff_schema"] == HANDOFF_SCHEMA
    assert "legacy" not in handoff
    assert "raw_capture" not in handoff
    assert handoff["analysis"]["summary"] == "Phase 1 summary."
    assert handoff["source_url"] == record.source_url


def test_ep24_frame_opt_in_runs_before_summary_for_framed_record():
    document = phase0_document() | {
        "frames": [{"id": "frame-1", "timestamp_seconds": 1.0, "description": "fixture"}]
    }
    provider = SequencedProvider([
        MultimodalFrameProposal(denotation=["A campaign poster."]),
        MultimodalSummaryProposal(summary="EP24 summary."),
    ])
    record = run_phase1_text_record(
        document, provider=provider,
        config=Phase1TextConfig(
            enabled=True, discourse_enabled=False, project_profile="ep24",
            ep24_frame_analysis_enabled=True, model="fake-model",
        ),
    )
    assert len(provider.requests) == 2
    assert record.intermediate.frame_analysis
    assert "multimodal_synthesis" in record.intermediate.stage_outputs


def test_ep24_frame_opt_in_tolerates_text_only_record_and_ai26_stays_text_only():
    ep24_provider = SequencedProvider([MultimodalSummaryProposal(summary="EP24 text-only summary.")])
    ep24_record = run_phase1_text_record(
        phase0_document(), provider=ep24_provider,
        config=Phase1TextConfig(
            enabled=True, discourse_enabled=False, project_profile="ep24",
            ep24_frame_analysis_enabled=True, model="fake-model",
        ),
    )
    assert len(ep24_provider.requests) == 1
    assert ep24_record.intermediate.stage_outputs["modality_plan"][-1]["is_text_only"] is True
    assert "frame_analysis_skipped" not in ep24_record.intermediate.stage_outputs

    provider = SequencedProvider([MultimodalSummaryProposal(summary="AI26 summary.")])
    record = run_phase1_text_record(
        phase0_document(), provider=provider,
        config=Phase1TextConfig(
            enabled=True, discourse_enabled=False, project_profile="ai26",
            ep24_frame_analysis_enabled=True, model="fake-model",
        ),
    )
    assert len(provider.requests) == 1
    assert "frame_analysis_skipped" not in record.intermediate.stage_outputs
    assert not record.intermediate.frame_analysis
