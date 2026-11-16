"""Issue #459 (residual, canonical path): the analysis must record WHICH codebook produced it.

Measured on the frozen Laskin corpus (5,304 records): ``analysis.codebook_refs``
non-empty 0, ``model_runs[].codebook_revision`` set 0, and
``intermediate.stage_outputs.phase1_codebook_context`` absent from every record.

The landed #462 fixed the narrow cause -- ``AI26Handler`` never set the declared
revision fields -- and recorded the merged codebook's identity. What it does not
cover, and what these tests pin, is:

1. the **canonical** Phase 1 path (``run_canonical_pipeline``, which produced the
   live AI26 corpus) still writes no ``phase1_codebook_context`` record at all;
2. a direct caller of that pipeline still stores ``codebook_revision = ""``,
   because only the worker path was given a value;
3. the **public/private layer precedence** (base id + overlay id + merged hash) is
   recorded nowhere, so a merged codebook still hides which layer produced a label.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION, CanonicalRecord
from laclaugpt_data_analysis.canonical_pipeline import (
    DiscourseProposal,
    MultimodalSummaryProposal,
    PipelineContext,
    run_canonical_pipeline,
)
from laclaugpt_data_analysis.codebooks import (
    CodebookEntry,
    entries_fingerprint,
    load_codebook,
)
from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.distributed_worker import (
    AI26_MODEL,
    AI26Handler,
    FrozenRunManifest,
    WorkerBinding,
)
from laclaugpt_data_analysis.freeze_run import (
    build_effective_codebook,
    effective_codebook_layers,
    write_run_manifest,
)
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse

# ---------------------------------------------------------------------------
# Fixtures: a synthetic record, a provider that answers the two model stages
# ---------------------------------------------------------------------------


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


def _provider() -> SequencedProvider:
    summary = MultimodalSummaryProposal(
        summary="Synthetic summary of a synthetic item.",
        narrative="A synthetic item used to exercise codebook provenance.",
        topics=["codebook provenance"],
        entities=["Synthetic Lab"],
    )
    return SequencedProvider([summary, DiscourseProposal()])


def _record() -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/item/459",
        source={"platform": "synthetic"},
        content={
            "title": "Synthetic AI debate",
            "text": "AI should serve democratic society, and critical AI names the risk.",
        },
    )


def _entries() -> list[CodebookEntry]:
    return [
        CodebookEntry(kind="formation", label="critical_ai", aliases=["critical AI"]),
        CodebookEntry(kind="formation", label="accelerationist", definition="Growth-first."),
    ]


def _run(entries, *, context=None) -> CanonicalRecord:
    return run_canonical_pipeline(
        _record(),
        provider=_provider(),
        context=context or PipelineContext(project_config={"analysis": {"laclau": True}}),
        codebook_entries=entries,
        model="fake-model",
        project_profile="ai26",
    )


# ---------------------------------------------------------------------------
# 1. A fingerprint of the priors, not of the document
# ---------------------------------------------------------------------------


def test_entries_fingerprint_is_order_insensitive_and_content_sensitive() -> None:
    entries = _entries()
    assert entries_fingerprint(entries) == entries_fingerprint(list(reversed(entries)))
    changed = [entries[0].model_copy(update={"definition": "edited"}), entries[1]]
    assert entries_fingerprint(entries) != entries_fingerprint(changed)


def test_entries_fingerprint_distinguishes_empty_from_populated() -> None:
    assert entries_fingerprint([]) == hashlib.sha256(b"[]").hexdigest()
    assert entries_fingerprint(_entries()) != entries_fingerprint([])


# ---------------------------------------------------------------------------
# 2. The canonical path records the revision and the stage
# ---------------------------------------------------------------------------


def test_direct_caller_stores_the_supplied_codebook_revision() -> None:
    result = _run(_entries())
    expected = entries_fingerprint(_entries())
    assert result.analysis.model_runs, "the pipeline must have made model calls"
    for run in result.analysis.model_runs:
        assert run["codebook_revision"] == expected
        assert run["codebook_provenance"]["source"] == "entries_supplied_to_prompt"


def test_codebook_context_stage_records_selection_not_run() -> None:
    result = _run(_entries())
    audit = result.intermediate.stage_outputs["phase1_codebook_context"][-1]
    assert audit["enabled"] is True
    assert audit["entry_count"] == 2
    assert audit["entries_sha256"] == entries_fingerprint(_entries())
    # The canonical Phase 1 path supplies the whole codebook as context and runs no
    # per-item selection; that is why analysis.codebook_refs is empty.
    assert audit["selected_entries"] == []
    assert audit["selection_method"].startswith("per_item_selection_not_run")
    assert audit["codebook_revision_source"] == "entries_content_fingerprint"
    assert result.analysis.codebook_refs == []


def test_codebook_context_stage_is_recorded_even_with_no_entries() -> None:
    result = _run([])
    audit = result.intermediate.stage_outputs["phase1_codebook_context"][-1]
    assert audit["enabled"] is False
    assert audit["selection_method"] == "no_codebook_entries_supplied"
    assert audit["entry_count"] == 0
    assert audit["codebook_revision_source"] == "none"
    # No codebook was supplied: the honest value is empty, not a fabricated hash.
    assert audit["codebook_revision"] == ""
    assert all(run["codebook_revision"] == "" for run in result.analysis.model_runs)


def test_worker_supplied_revision_is_preserved_and_named() -> None:
    frozen = "frozen-effective-codebook-sha256"
    result = _run(_entries(), context=PipelineContext(
        project_config={"analysis": {"laclau": True}},
        codebook_revision=frozen,
        codebook_provenance={
            "frozen_file_sha256": frozen,
            "effective": {"codebook_id": "ai26-effective"},
        },
    ))
    assert all(run["codebook_revision"] == frozen for run in result.analysis.model_runs)
    audit = result.intermediate.stage_outputs["phase1_codebook_context"][-1]
    assert audit["codebook_revision"] == frozen
    # The two revision quantities are not interchangeable; the audit names the one
    # it holds rather than leaving a reader to guess.
    assert audit["codebook_revision_source"] == "run_manifest_file_sha256"
    assert audit["codebook"]["effective"]["codebook_id"] == "ai26-effective"


# ---------------------------------------------------------------------------
# 3. Freeze records the layers, and the worker carries them onto the context
# ---------------------------------------------------------------------------


def _codebook_file(path: Path, *, codebook_id: str, label: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "codebook_id": codebook_id,
                "version": "1",
                "title": codebook_id,
                "entries": [
                    {"kind": "formation", "label": label, "definition": f"{codebook_id} entry"}
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _frozen_run(tmp_path: Path) -> tuple[Path, Path, dict, list[dict]]:
    private = tmp_path / "private"
    private.mkdir()
    public = _codebook_file(tmp_path / "public.json", codebook_id="ai26-public", label="critical_ai")
    overlay = _codebook_file(tmp_path / "overlay.json", codebook_id="ai26-overlay", label="sovereign_ai")
    config = private / "analysis.json"
    config.write_text('{"analysis": {}}', encoding="utf-8")
    effective_path = build_effective_codebook(
        public_codebook=public, private_overlay=overlay, output=private / "codebook.json"
    )
    layers = effective_codebook_layers(public_codebook=public, private_overlay=overlay)
    manifest = write_run_manifest(
        private_root=private,
        analysis_config=config,
        codebook=effective_path,
        run_id="run-459",
        public_git_sha="test-sha",
        codebook_layers=layers,
    )
    return effective_path, config, manifest, layers


def test_freeze_manifest_records_the_layer_identities(tmp_path: Path) -> None:
    effective_path, _config, manifest, _layers = _frozen_run(tmp_path)
    effective = load_codebook(effective_path)

    assert manifest["codebook_fingerprint"] == effective.fingerprint()
    assert manifest["codebook_id"] == "ai26-effective"
    assert [layer["role"] for layer in manifest["codebook_layers"]] == ["base", "overlay"]
    assert [layer["codebook_id"] for layer in manifest["codebook_layers"]] == [
        "ai26-public",
        "ai26-overlay",
    ]
    # Both layer hashes are recorded, so "which of the two produced this label" is
    # answerable without the private inputs in hand.
    assert len({layer["sha256"] for layer in manifest["codebook_layers"]}) == 2


def test_worker_context_carries_the_layers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "laclaugpt_data_analysis.distributed_worker.resolve_llm_host", lambda: None
    )
    effective_path, config, manifest, _layers = _frozen_run(tmp_path)
    private = effective_path.parent
    manifest_path = private / "run.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    binding = WorkerBinding.build(
        manifest_path=manifest_path,
        private_root=private,
        private_config=config,
        codebook=effective_path,
        worker_id="worker-459",
    )
    handler = AI26Handler(
        binding,
        Settings(project_id="ai26", data_backend="csv", cache_backend="none"),
        object(),
    )

    context = handler.context
    assert context.codebook_revision == manifest["codebook_sha256"]
    assert context.codebook_provenance["effective"]["codebook_id"] == "ai26-effective"
    assert [layer["role"] for layer in context.codebook_provenance["layers"]] == [
        "base",
        "overlay",
    ]
    assert context.codebook_provenance["frozen_file_sha256"] == manifest["codebook_sha256"]
    assert context.codebook_provenance["frozen_fingerprint"] == manifest["codebook_fingerprint"]
    # And the manifest's own revisions still reach provenance (issue #159 guard).
    joined = json.dumps(context.provenance)
    assert manifest["config_sha256"] in joined
    assert manifest["codebook_sha256"] in joined
    assert load_codebook(effective_path).fingerprint() in joined


def test_manifest_without_layers_still_loads(tmp_path: Path) -> None:
    """Manifests frozen before this change carry no layer fields; they must still load."""
    manifest = FrozenRunManifest(
        project_id="ai26",
        run_id="legacy",
        schema_version=SCHEMA_VERSION,
        config_sha256="c",
        codebook_sha256="k",
        model=AI26_MODEL,
        public_git_sha="sha",
    )
    assert manifest.codebook_layers == ()
    assert manifest.codebook_fingerprint == ""
