"""#459: a stored analysis must say which codebook produced it.

The corpus could not tell a public-only run from a public+overlay run, or a run
with the codebook in force from one without: `analysis.codebook_refs` and
`model_runs[].codebook_revision` were empty on every record. These tests pin the
two things a record must now be able to answer:

  * which effective codebook (merged fingerprint), and
  * which layers it was merged from (base / overlay), with the precedence stated.
"""
from __future__ import annotations

import json
from pathlib import Path

from laclaugpt_data_analysis.canonical_pipeline import MultimodalSummaryProposal
from laclaugpt_data_analysis.codebooks import (
    Codebook,
    CodebookEntry,
    load_codebook,
    load_effective_codebook,
)
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.phase1_runtime import Phase1TextConfig, run_phase1_text_record

REPO = Path(__file__).resolve().parents[1]
PUBLIC = REPO / "codebooks" / "public" / "ai26_v2.yaml"


class Provider:
    def __init__(self):
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.requests.append(request)
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
    return {
        "source_url": "https://example.org/459",
        "normalized_text": "Democratic AI needs accountable governance.",
    }


def config(**overrides):
    return Phase1TextConfig(enabled=True, model="fake", **overrides)


def test_supplying_a_codebook_names_the_run_without_switching_context_on():
    effective, _ = load_effective_codebook(PUBLIC)
    provider = Provider()

    record = run_phase1_text_record(
        document(), provider=provider, config=config(), codebook=effective
    )

    audit = record.intermediate.stage_outputs["phase1_codebook_context"][0]
    assert audit["enabled"] is False  # behaviour unchanged
    assert audit["full_codebook_revision_known"] is True
    assert audit["codebook_revision"] == effective.fingerprint()
    assert audit["codebook"]["effective"]["codebook_id"] == effective.codebook_id
    # A pre-merged object cannot name its layers; "effective" is the honest claim.
    assert audit["codebook"]["precedence"] == ["effective"]
    assert [layer["role"] for layer in audit["codebook"]["layers"]] == ["effective"]
    assert record.analysis.codebook_refs == []
    # The prompt still received no codebook context.
    assert "accountable governance" in provider.requests[0].user_prompt
    assert "ai26-public-v2" not in provider.requests[0].user_prompt


def test_the_revision_reaches_every_model_run_not_only_the_audit_trail():
    effective, _ = load_effective_codebook(PUBLIC)

    record = run_phase1_text_record(
        document(),
        provider=Provider(),
        config=config(codebook_context_enabled=True),
        codebook=effective,
    )

    assert record.analysis.model_runs, "the summary stage must have produced a run"
    assert {run["codebook_revision"] for run in record.analysis.model_runs} == {
        effective.fingerprint()
    }
    assert all(run["codebook_provenance"]["effective"]["sha256"] for run in record.analysis.model_runs)


def test_selection_labels_are_recorded_separately_from_the_book():
    effective = Codebook(
        codebook_id="fixture-book",
        version="1",
        title="Fixture codebook",
        entries=[
            CodebookEntry(kind="signifier", label="democratic AI"),
            CodebookEntry(kind="signifier", label="absent concept"),
        ],
    )

    record = run_phase1_text_record(
        document(),
        provider=Provider(),
        config=config(codebook_context_enabled=True),
        codebook=effective,
    )

    audit = record.intermediate.stage_outputs["phase1_codebook_context"][0]
    assert record.analysis.codebook_refs
    assert audit["codebook_context_sha256"] != audit["codebook_revision"]


def test_an_overlay_is_named_and_the_precedence_is_stated(tmp_path):
    overlay = tmp_path / "private_overlay.yaml"
    payload = load_codebook(PUBLIC).model_dump(mode="json")
    payload.update(
        {
            "codebook_id": "private-overlay",
            "version": "1",
            "title": "Private overlay",
            "entries": [{"kind": "signifier", "label": "democratic AI", "aliases": []}],
        }
    )
    overlay.write_text(json.dumps(payload), encoding="utf-8")

    effective, provenance = load_effective_codebook(PUBLIC, overlay)

    assert provenance["precedence"] == ["base", "overlay"]
    assert [layer["role"] for layer in provenance["layers"]] == ["base", "overlay"]
    assert provenance["merged_sha256"] == effective.fingerprint()
    assert provenance["layers"][0]["sha256"] != provenance["layers"][1]["sha256"]

    # The configured path is how a deployment names its layers; a pre-merged object
    # cannot tell the runtime which layers produced it.
    record = run_phase1_text_record(
        document(),
        provider=Provider(),
        config=config(
            codebook_path=str(PUBLIC), codebook_overlay_path=str(overlay)
        ),
    )
    audit = record.intermediate.stage_outputs["phase1_codebook_context"][0]
    assert audit["codebook"]["precedence"] == ["base", "overlay"]
    assert audit["codebook_revision"] == effective.fingerprint()


def test_entries_without_a_book_say_the_revision_is_unknown():
    record = run_phase1_text_record(
        document(),
        provider=Provider(),
        config=config(codebook_context_enabled=True),
        codebook_entries=[CodebookEntry(kind="signifier", label="democratic AI")],
    )

    audit = record.intermediate.stage_outputs["phase1_codebook_context"][0]
    assert audit["full_codebook_revision_known"] is False
    assert audit["codebook_revision"] == ""
    assert audit["codebook"] == {}
    # The selected labels are still known, and are recorded as such.
    assert record.analysis.codebook_refs == ["democratic AI"]
    # A fragment hash must never be presented as the book's revision.
    assert all(run["codebook_revision"] == "" for run in record.analysis.model_runs)
