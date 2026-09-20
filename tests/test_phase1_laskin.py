import json

from laclaugpt_data_analysis.canonical_pipeline import MultimodalSummaryProposal
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.phase1_laskin import phase1_laskin_preflight, run_bounded_phase1
from laclaugpt_data_analysis.phase1_runtime import Phase1TextConfig


class FakeProvider:
    def __init__(self):
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.requests.append(request)
        payload = MultimodalSummaryProposal(summary="Phase 1 bounded summary.")
        return LLMResponse(
            content=payload.model_dump_json(),
            provenance=LLMCallProvenance(
                requested_mode="local",
                requested_model="fake",
                resolved_model="fake",
                actual_mode="local",
                actual_model="fake",
                endpoint="fake",
            ),
        )


def _doc(index: int):
    return {
        "source_url": f"https://example.org/{index}",
        "document_id": f"doc-{index}",
        "normalized_text": f"AI text {index}.",
        "phase0_summary": {"summary": f"Phase 0 {index}."},
    }


def test_preflight_is_text_only_and_phase2_off(tmp_path):
    path = tmp_path / "sample.jsonl"
    path.write_text(json.dumps(_doc(1)) + "\n", encoding="utf-8")
    report = phase1_laskin_preflight(
        input_path=path,
        config=Phase1TextConfig(enabled=False, discourse_enabled=False, project_profile="ai26"),
    )

    assert report["status"] == "ok"
    assert report["text_only"] is True
    assert report["multimodal_required"] is False
    assert report["browser_required"] is False
    assert report["phase2_enabled"] is False


def test_preflight_rejects_discourse_without_phase1(tmp_path):
    path = tmp_path / "sample.jsonl"
    path.write_text(json.dumps(_doc(1)) + "\n", encoding="utf-8")
    report = phase1_laskin_preflight(
        input_path=path,
        config=Phase1TextConfig(enabled=False, discourse_enabled=True, project_profile="ai26"),
    )

    assert report["status"] == "invalid"
    assert any("discourse cannot be enabled" in item for item in report["problems"])


def test_bounded_runner_caps_records_and_preserves_phase0():
    provider = FakeProvider()
    config = Phase1TextConfig(
        enabled=True,
        discourse_enabled=False,
        model="fake",
        project_profile="ai26",
    )
    outputs, status = run_bounded_phase1(
        [_doc(1), _doc(2), _doc(3)],
        provider=provider,
        config=config,
        max_records=2,
    )

    assert status["processed"] == 2
    assert status["succeeded"] == 2
    assert status["failed"] == 0
    assert status["phase2_enabled"] is False
    assert len(provider.requests) == 2
    payload = json.loads(outputs[0])
    assert payload["analysis"]["summary"] == "Phase 1 bounded summary."
    assert payload["legacy"]["phase0"]["phase0_summary"]["summary"] == "Phase 0 1."
