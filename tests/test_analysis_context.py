from __future__ import annotations

from laclaugpt_data_analysis.analysis_context import build_analysis_context_bundle
from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.codebooks import CodebookEntry


def test_bundle_separates_current_evidence_from_context_memory() -> None:
    record = CanonicalRecord(source_url="https://example.org/item")
    record.content.text = "Current document evidence"
    bundle = build_analysis_context_bundle(
        record,
        task="Return structured discourse candidates.",
        project_background="Project background",
        theory_context="Theory context",
        situational_summary="Previous daily summary",
        memory_context="Prior accepted record",
        rag_context="Retrieved related record",
        codebook_entries=[CodebookEntry(kind="actor", label="Example actor")],
    )

    assert bundle.current_source.evidence_role == "source_evidence"
    assert bundle.current_source.trust == "source"
    assert bundle.situational_summary.evidence_role == "context"
    assert bundle.situational_summary.trust == "context_not_evidence"
    assert bundle.rag_context.trust == "context_not_evidence"
    assert bundle.codebook_context.trust == "researcher_context"
    assert "not proof" in bundle.codebook_context.text.lower()


def test_bundle_maps_to_canonical_prompt_envelope_with_hash_provenance() -> None:
    record = CanonicalRecord(source_url="https://example.org/item")
    record.content.text = "Source text"
    bundle = build_analysis_context_bundle(
        record,
        task="Analyse the current source only.",
        project_background="AI26 background",
        theory_context="Evidence-first theory",
        source_profile="Researcher-provided source profile",
        situational_summary="Historical summary",
        memory_context="Memory",
        rag_context="RAG",
    )
    envelope = bundle.prompt_envelope(record, prompt_version="test-v1")
    rendered = envelope.render()

    assert "[PROJECT CONTEXT]" in rendered
    assert "AI26 background" in rendered
    assert "Evidence-first theory" in rendered
    assert "[CURRENT SOURCE ITEM]" in rendered
    assert "Source text" in rendered
    assert "[RAG CONTEXT]" in rendered
    assert "role=context" in rendered
    assert "sha256=" in rendered

    audit = bundle.audit_snapshot()
    assert audit["fragments"]["current_source"]["evidence_role"] == "source_evidence"
    assert audit["fragments"]["rag_context"]["evidence_role"] == "context"
    assert audit["fragments"]["task_contract"]["evidence_role"] == "task_contract"
