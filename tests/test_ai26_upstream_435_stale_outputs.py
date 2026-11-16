"""Stale-output contracts for AI26's optional stages (issue #435, item 2).

Upstream #410's rule, in its own words: clear the previous outputs when retrying, because empty JSON
and no-evidence responses must not preserve earlier assertions. AI26 keeps a plugin's *latest* result
in ``analysis.plugin_results`` and an append-only history in ``intermediate.stage_outputs``, so the
stale case is not "old edges survive a merge" but "the current result and the latest run disagree".

These tests pin both halves for the optional DNA stage and for the graph projection:

* a successful re-run with no statements replaces the earlier statements (no stale claims);
* a failed re-run records the failure, adds no statements and no history entry;
* the graph projection contains only what the record currently asserts.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord, DiscourseObject, Evidence, Relation
from laclaugpt_data_analysis.canonical_pipeline import PipelineContext
from laclaugpt_data_analysis.dna_statement_coding import (
    DNAConceptCandidate,
    DNAEntityCandidate,
    DNAStatementBatch,
    DNAStatementCandidate,
    run_optional_dna_statement_coding,
)
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.stages.graph import build_discourse_graph

TEXT = "Ada Example said: open-source models should remain legally available."


class StubProvider:
    """Returns the queued payloads in order; raises whatever is queued instead of a payload."""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.requests.append(request)
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return LLMResponse(
            content=payload.model_dump_json(),
            provenance=LLMCallProvenance(
                requested_mode="local",
                requested_model=request.model,
                resolved_model=request.model,
                actual_mode="local",
                actual_model=request.model,
                endpoint="fake",
            ),
        )


def record() -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/dna/stale-1",
        source_native_ids={"synthetic": "doc-1"},
        raw_capture={"payload": {"synthetic": True}},
        source={"platform": "synthetic", "language": "en",
                "created_at": datetime(2026, 11, 16, tzinfo=UTC)},
        content={"text": TEXT},
    )


def candidate(text: str) -> DNAStatementBatch:
    start = text.index("open-source models")
    return DNAStatementBatch(statements=[DNAStatementCandidate(
        person=DNAEntityCandidate(label="Ada Example"),
        concept=DNAConceptCandidate(label="open-source models"),
        agreement=True,
        agreement_status="coded",
        evidence_text="open-source models should remain legally available",
        start=start,
        stop=start + len("open-source models should remain legally available"),
        confidence=0.9,
    )])


def context():
    return PipelineContext(
        codebook_revision="ai26-codebook-v2",
        project_config={
            "analysis_phase": 2,
            "analysis": {"dna_statement_coding": {
                "enabled": True, "model": "gemma4:test", "prompt_version": "v1",
                "require_binary_agreement": False, "duplicate_policy": "preserve",
                "concept_mode": "codebook_or_provisional",
            }},
        },
    )


def test_a_second_run_with_no_statements_replaces_the_first_results():
    item = record()
    provider = StubProvider([candidate(TEXT), DNAStatementBatch(statements=[])])

    first = run_optional_dna_statement_coding(item, provider=provider, context=context(), model="m")
    second = run_optional_dna_statement_coding(item, provider=provider, context=context(), model="m")

    assert first is not None and len(first) == 1
    assert second == []
    current = item.analysis.plugin_results["dna_statement_coding"]
    assert current["proposal"]["statements"] == [], "an empty re-run must displace the old statements"
    history = item.intermediate.stage_outputs["dna_statement_coding"]
    assert len(history) == 2, "history keeps both runs; the current result is the latest"


def test_a_failed_retry_records_the_failure_and_adds_nothing():
    item = record()
    provider = StubProvider([candidate(TEXT), RuntimeError("provider truncated twice")])

    run_optional_dna_statement_coding(item, provider=provider, context=context(), model="m")
    with pytest.raises(RuntimeError):
        run_optional_dna_statement_coding(item, provider=provider, context=context(), model="m")

    failure = item.analysis.plugin_failures["dna_statement_coding"]
    assert failure["error"] == "RuntimeError"
    assert failure["result_preserved"] is True, "the operator must be able to tell what is on screen"
    assert len(item.analysis.plugin_results["dna_statement_coding"]["proposal"]["statements"]) == 1
    assert len(item.intermediate.stage_outputs["dna_statement_coding"]) == 1, \
        "a failed run is not a run: no history entry is invented"


def test_a_first_run_that_fails_preserves_nothing_and_says_so():
    item = record()
    provider = StubProvider([RuntimeError("no provider")])
    with pytest.raises(RuntimeError):
        run_optional_dna_statement_coding(item, provider=provider, context=context(), model="m")
    assert item.analysis.plugin_failures["dna_statement_coding"]["result_preserved"] is False
    assert "dna_statement_coding" not in item.analysis.plugin_results


def test_the_stage_stays_disabled_unless_asked():
    item = record()
    provider = StubProvider([])
    result = run_optional_dna_statement_coding(
        item, provider=provider, context=PipelineContext(project_config={"project": "ai26"}),
        model="m")
    assert result is None
    assert provider.requests == []
    assert "dna_statement_coding" not in item.analysis.plugin_results


def test_the_graph_projection_carries_only_current_assertions():
    item = record()
    empty_graph = build_discourse_graph(item)
    assert empty_graph["edges"] == []

    item.evidence.append(Evidence(
        evidence_id="ev-1", kind="quote", source_url=item.source_url,
        quote="open-source models should remain legally available"))
    item.analysis.us.append(DiscourseObject(object_id="us-1", kind="us", label="the people"))
    graph = build_discourse_graph(item)
    assert any(edge["type"] == "EVIDENCE_IN" for edge in graph["edges"])

    item.evidence.clear()
    rebuilt = build_discourse_graph(item)
    assert rebuilt["edges"] == [], "reprojecting after the evidence is gone leaves no stale edges"


def test_graph_edges_never_point_at_relation_ids():
    """A dangling reference materialises as a phantom node on GraphML export."""
    item = record()
    item.evidence.append(Evidence(evidence_id="ev-1", kind="quote",
                                  source_url=item.source_url, quote="x"))
    item.analysis.relations.append(Relation(
        relation_id="rel-1", relation_type="equivalence", source_ref="us-1",
        target_ref="them-1", evidence_ids=["ev-1"]))
    graph = build_discourse_graph(item)
    relation_ids = {relation.relation_id for relation in item.analysis.relations}
    for edge in graph["edges"]:
        assert edge["target"] not in relation_ids, "an edge may not target a relation id"
