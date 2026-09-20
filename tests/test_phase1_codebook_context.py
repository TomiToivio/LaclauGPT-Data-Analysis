from laclaugpt_data_analysis.canonical_pipeline import MultimodalSummaryProposal
from laclaugpt_data_analysis.codebooks import CodebookEntry
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.phase1_runtime import (
    Phase1TextConfig,
    run_phase1_text_record,
    select_relevant_codebook_entries,
)


class Provider:
    def __init__(self):
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content=MultimodalSummaryProposal(summary="Fixture summary.").model_dump_json(),
            provenance=LLMCallProvenance(
                requested_mode="local", requested_model="fake", resolved_model="fake",
                actual_mode="local", actual_model="fake", endpoint="fixture",
            ),
        )


def document():
    return {
        "source_url": "https://example.org/item",
        "normalized_text": "Democratic AI needs accountable governance.",
    }


def entries():
    return [
        CodebookEntry(kind="signifier", label="democratic AI", aliases=["democratic artificial intelligence"]),
        CodebookEntry(kind="signifier", label="accountable governance"),
        CodebookEntry(kind="signifier", label="unrelated concept"),
    ]


def test_selection_uses_only_current_source_label_or_alias_matches():
    record = run_phase1_text_record(document(), provider=Provider())
    assert [entry.label for entry in select_relevant_codebook_entries(record, entries())] == [
        "democratic AI", "accountable governance"
    ]


def test_codebook_context_is_opt_in_and_not_memory_or_source_evidence():
    disabled = Provider()
    run_phase1_text_record(
        document(), provider=disabled,
        config=Phase1TextConfig(enabled=True, model="fake"), codebook_entries=entries(),
    )
    assert "unrelated concept" not in disabled.requests[0].user_prompt
    assert "democratic AI" not in disabled.requests[0].user_prompt

    enabled = Provider()
    record = run_phase1_text_record(
        document(), provider=enabled,
        config=Phase1TextConfig(enabled=True, codebook_context_enabled=True, model="fake"),
        codebook_entries=entries(),
    )
    prompt = enabled.requests[0].user_prompt
    assert "democratic AI" in prompt
    assert "accountable governance" in prompt
    assert "unrelated concept" not in prompt
    assert "researcher/context priors, not proof" in prompt
    assert "role=context" in prompt
    assert "[MEMORY CONTEXT]" in prompt
    assert record.intermediate.stage_outputs["phase1_codebook_context"][0]["evidence_role"] == "researcher_context"
