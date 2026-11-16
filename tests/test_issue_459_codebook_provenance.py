"""Issue #459: a stored analysis must say which codebook produced it.

The AI26 corpus had `codebook_refs` empty on all 5,304 records and
`model_runs[].codebook_revision` empty on all of them, because the distributed worker built
its `PipelineContext` without setting the declared `config_revision` / `codebook_revision`
fields — the manifest revisions were carried only in `provenance`, which no stage reads for
those fields. Two consequences followed: a record could not be attributed to a codebook, and
"the codebook-context stage never ran" was indistinguishable from "it ran and selected
nothing".
"""
from __future__ import annotations

from types import SimpleNamespace

from laclaugpt_data_analysis.codebooks import Codebook, CodebookEntry, merge_codebooks
from laclaugpt_data_analysis.distributed_worker import _analysis_context, _codebook_identity
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.phase1_runtime import Phase1TextConfig, run_phase1_text_record
from laclaugpt_data_analysis.stages.shared import model_run_metadata


def codebook() -> Codebook:
    return Codebook(
        codebook_id="ai26-test",
        version="1.2.3",
        title="Fixture codebook",
        entries=[
            CodebookEntry(kind="signifier", label="democratic AI"),
            CodebookEntry(kind="signifier", label="accountable governance"),
        ],
    )


def binding():
    manifest = SimpleNamespace(config_sha256="config-sha", codebook_sha256="codebook-sha")
    return SimpleNamespace(manifest=manifest)


def test_context_carries_the_manifest_revisions():
    context = _analysis_context(binding(), {"capabilities": {}}, codebook())
    assert context.codebook_revision == "codebook-sha"
    assert context.config_revision == "config-sha"


def test_model_run_metadata_records_the_codebook_revision_not_an_empty_string():
    context = _analysis_context(binding(), {}, codebook())
    provenance = LLMCallProvenance(
        requested_mode="local",
        requested_model="fake",
        resolved_model="fake",
        actual_mode="local",
        actual_model="fake",
        endpoint="fixture",
    )
    response = LLMResponse(content="{}", provenance=provenance)
    metadata = model_run_metadata(
        context,
        response,
        {"prompt_sha256": "x"},
        prompt_version="test.v1",
        stage="discourse",
    )
    assert metadata["codebook_revision"] == "codebook-sha"
    assert metadata["config_revision"] == "config-sha"


def test_context_provenance_names_the_codebook_not_just_its_hash():
    context = _analysis_context(binding(), {}, codebook())
    assert context.provenance["codebook_id"] == ["ai26-test"]
    assert context.provenance["codebook_version"] == ["1.2.3"]
    assert context.provenance["codebook_entries"] == ["2"]
    assert context.provenance["codebook_sha256"] == ["codebook-sha"]


def test_a_merged_codebook_reports_the_merged_identity():
    merged = merge_codebooks([codebook(), Codebook(
        codebook_id="arena-overlay", version="0.1", title="Overlay",
        entries=[CodebookEntry(kind="signifier", label="frontier pacing")],
    )], codebook_id="ai26-effective")
    identity = _codebook_identity(merged)
    assert identity["codebook_id"] == ["ai26-effective"]
    assert identity["codebook_version"][0].startswith("merged-")
    assert identity["codebook_entries"] == ["3"]


class Provider:
    def chat(self, request: ChatRequest) -> LLMResponse:
        from laclaugpt_data_analysis.canonical_pipeline import MultimodalSummaryProposal

        return LLMResponse(
            content=MultimodalSummaryProposal(summary="Fixture summary.").model_dump_json(),
            provenance=LLMCallProvenance(
                requested_mode="local",
                requested_model="fake",
                resolved_model="fake",
                actual_mode="local",
                actual_model="fake",
                endpoint="fixture",
            ),
        )


def document():
    return {"source_url": "https://example.org/item", "normalized_text": "Democratic AI needs governance."}


def test_disabled_selection_is_recorded_as_disabled_not_as_absent():
    record = run_phase1_text_record(
        document(),
        provider=Provider(),
        config=Phase1TextConfig(enabled=True, model="fake", codebook_context_enabled=False),
        codebook_entries=codebook().entries,
    )
    block = record.intermediate.stage_outputs["phase1_codebook_context"][0]
    assert block["enabled"] is False
    assert block["selection_method"] == "disabled"
    assert block["selected_entries"] == []
    assert block["codebook_entries_offered"] == 2


def test_enabled_selection_with_no_match_is_distinguishable_from_disabled():
    record = run_phase1_text_record(
        document(),
        provider=Provider(),
        config=Phase1TextConfig(enabled=True, model="fake", codebook_context_enabled=True),
        codebook_entries=[CodebookEntry(kind="signifier", label="unrelated concept")],
    )
    block = record.intermediate.stage_outputs["phase1_codebook_context"][0]
    assert block["enabled"] is True
    assert block["selection_method"] == "current_source_label_or_alias_match"
    assert block["selected_entries"] == []
