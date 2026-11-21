"""Issue #460: the evidence gate — a coded field must point at a span that resolves.

The gate consumes a fact the pipeline already records (`Evidence.metadata["exact"]`, set by
`locate_quote()` in `stages/evidence.py`) and that nothing used: an object whose every quotation
failed to locate was stored beside one whose quotation resolved.

It is off by default because turning it on changes what the instrument emits — a decision in
`docs/AI26_OPEN_DECISIONS.md` D4, not a default. These tests pin both the on and the off behaviour,
and pin that `dry_run` measures without mutating, so the decision can be taken against the live
corpus.
"""
from __future__ import annotations

from laclaugpt_data_analysis.canonical import (
    AnalysisSection,
    CanonicalRecord,
    ContentSection,
    DiscourseObject,
    Evidence,
    Relation,
    SourceSection,
)
from laclaugpt_data_analysis.evidence_gate import (
    ENV_FLAG,
    apply_evidence_gate,
    evidence_gate_enabled,
)


def record_with(
    *,
    exact_quote: str | None = "The source says this sentence.",
    bad_quote: str | None = "A sentence that is not in the source at all.",
) -> CanonicalRecord:
    record = CanonicalRecord(
        source_url="https://example.org/item",
        source=SourceSection(),
        content=ContentSection(text="The source says this sentence."),
    )
    if exact_quote is not None:
        record.evidence.append(
            Evidence(
                evidence_id="formation:1:evidence:1",
                kind="llm_proposed_source_evidence",
                source_url=record.source_url,
                quote=exact_quote,
                metadata={"exact": True},
            )
        )
    if bad_quote is not None:
        record.evidence.append(
            Evidence(
                evidence_id="signifier:1:evidence:2",
                kind="llm_proposed_source_evidence",
                source_url=record.source_url,
                quote=bad_quote,
                metadata={"exact": False},
            )
        )
    record.analysis.formations = [
        DiscourseObject(object_id="formation:1", label="democratic AI", kind="formation",
                        evidence_ids=["formation:1:evidence:1"]),
    ]
    record.analysis.signifiers = [
        DiscourseObject(object_id="signifier:1", label="unbacked signifier", kind="signifier",
                        evidence_ids=["signifier:1:evidence:2"]),
    ]
    return record


def test_an_object_with_a_resolving_span_is_kept():
    record = record_with()
    report = apply_evidence_gate(record)
    assert [obj.label for obj in record.analysis.formations] == ["democratic AI"]
    assert report["fields"]["formations"]["dropped"] == 0


def test_an_object_whose_only_span_fails_to_locate_is_dropped_and_named():
    record = record_with()
    report = apply_evidence_gate(record)
    assert record.analysis.signifiers == []
    assert report["fields"]["signifiers"]["dropped"] == 1
    assert "signifiers:unbacked signifier" in " ".join(record.analysis.uncertainty)


def test_the_failed_evidence_is_never_deleted():
    """The audit trail keeps the quote that did not resolve: that is a finding, not noise."""
    record = record_with()
    before = len(record.evidence)
    apply_evidence_gate(record)
    assert len(record.evidence) == before


def test_an_object_with_no_evidence_ids_at_all_is_dropped():
    record = record_with()
    record.analysis.nodal_points = [
        DiscourseObject(object_id="nodal_points:1", label="AI", kind="nodal_point", evidence_ids=[]),
    ]
    report = apply_evidence_gate(record)
    assert record.analysis.nodal_points == []
    assert report["fields"]["nodal_points"]["dropped"] == 1


def test_relations_are_gated_too():
    record = record_with()
    record.analysis.antagonisms = [
        Relation(relation_id="antagonisms:1", relation_type="antagonism",
                 source_ref="us", target_ref="them", evidence_ids=["signifier:1:evidence:2"]),
        Relation(relation_id="antagonisms:2", relation_type="antagonism",
                 source_ref="us", target_ref="them", evidence_ids=["formation:1:evidence:1"]),
    ]
    apply_evidence_gate(record)
    assert [relation.relation_id for relation in record.analysis.antagonisms] == ["antagonisms:2"]


def test_dry_run_reports_the_same_counts_and_changes_nothing():
    record = record_with()
    report = apply_evidence_gate(record, dry_run=True)
    assert report["dropped_total"] == 1
    assert len(record.analysis.signifiers) == 1, "dry run must not mutate"
    assert record.analysis.uncertainty == [], "dry run must not write a note"


def test_gate_is_off_unless_asked(monkeypatch):
    monkeypatch.delenv(ENV_FLAG, raising=False)
    assert evidence_gate_enabled() is False
    monkeypatch.setenv(ENV_FLAG, "1")
    assert evidence_gate_enabled() is True
    monkeypatch.setenv(ENV_FLAG, "no")
    assert evidence_gate_enabled() is False


def test_explicit_argument_overrides_the_environment(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")
    assert evidence_gate_enabled(False) is False
    monkeypatch.delenv(ENV_FLAG, raising=False)
    assert evidence_gate_enabled(True) is True


def test_a_record_with_no_coded_fields_reports_nothing_dropped():
    record = CanonicalRecord(
        source_url="https://example.org/empty",
        source=SourceSection(),
        content=ContentSection(text=""),
    )
    report = apply_evidence_gate(record)
    assert report["dropped_total"] == 0
    assert report["fields"] == {}


def test_analysis_section_still_declares_the_fields_the_gate_touches():
    """If a field is renamed, the gate must not silently stop gating it."""
    from laclaugpt_data_analysis.evidence_gate import CODED_OBJECT_FIELDS, CODED_RELATION_FIELDS

    declared = set(AnalysisSection.model_fields)
    missing = (set(CODED_OBJECT_FIELDS) | set(CODED_RELATION_FIELDS)) - declared
    assert not missing, f"gate names fields that no longer exist: {sorted(missing)}"
