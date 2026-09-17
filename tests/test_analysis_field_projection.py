"""Guards against AnalysisSection fields that nothing ever writes (issue #108).

The canonical pipeline declared 38 analysis fields and wrote only 16, so the
discourse stage's equivalence/difference chains and floating/empty signifier
candidates were computed and then discarded. Empty lists validate fine, which is
why no test caught it.

This test pins the fields the canonical pipeline is responsible for, so
declaring a new field without projecting it fails loudly instead of silently
producing an empty list forever.
"""
from __future__ import annotations

import re
from pathlib import Path

from laclaugpt_data_analysis.canonical import AnalysisSection

REPO = Path(__file__).resolve().parents[1]
PIPELINE = REPO / "src" / "laclaugpt_data_analysis" / "canonical_pipeline.py"

# Fields the canonical AI26 pipeline is expected to project from its stage
# outputs. Anything added to AnalysisSection must be added here deliberately,
# together with the projection code that fills it.
PROJECTED_BY_CANONICAL_PIPELINE = {
    "abstentions",
    "affects",
    "antagonisms",
    "completed_at",
    "difference_chains",
    "empty_signifier_candidates",
    "entities",
    "equivalence_chains",
    "floating_signifiers",
    "formations",
    "formula_of_populism",
    "frontier",
    "imaginaries",
    "nodal_points",
    "relations",
    "signifiers",
    "started_at",
    "status",
    "summary",
    "uncertainty",
    "us",
}

# Fields deliberately owned by another layer (plugins, RDF, periodic summaries,
# the superseded legacy pipeline) or reserved for a future stage. Listed
# explicitly so the exclusion is a decision rather than an oversight.
NOT_PROJECTED_HERE = {
    "actor_entity_relations",
    "classifications",
    "codebook_refs",
    "discourses",
    "embeddings",
    "entity_mentions",
    "memory_refs",
    "model_runs",
    "plugin_failures",
    "plugin_results",
    "representations",
    "sentiments",
    "stances",
    "themes",
    "them",
    "topic_assignments",
    "topics",
}


def _declared_fields() -> set[str]:
    return set(AnalysisSection.model_fields)


def _written_fields() -> set[str]:
    """Fields assigned or extended on ``record.analysis`` in the pipeline."""
    text = PIPELINE.read_text(encoding="utf-8")
    written = set(re.findall(r"record\.analysis\.([a-z_]+)\s*=", text))
    written |= set(re.findall(r"record\.analysis\.([a-z_]+)\.extend", text))
    return written


def test_every_declared_field_is_classified() -> None:
    """A new AnalysisSection field must be either projected or explicitly exempt."""
    declared = _declared_fields()
    classified = PROJECTED_BY_CANONICAL_PIPELINE | NOT_PROJECTED_HERE
    unclassified = declared - classified
    assert not unclassified, (
        "New AnalysisSection field(s) with no decision about who writes them: "
        f"{sorted(unclassified)}. Add the projection, or list them in "
        "NOT_PROJECTED_HERE with the owning layer."
    )


def test_classification_only_names_real_fields() -> None:
    """Catch typos and fields that were removed from the contract."""
    declared = _declared_fields()
    stale = (PROJECTED_BY_CANONICAL_PIPELINE | NOT_PROJECTED_HERE) - declared
    assert not stale, f"classification lists fields that no longer exist: {sorted(stale)}"


def test_pipeline_actually_writes_the_projected_fields() -> None:
    """The fields this test calls 'projected' must really be assigned."""
    written = _written_fields()
    missing = PROJECTED_BY_CANONICAL_PIPELINE - written
    assert not missing, (
        "Declared as projected by the canonical pipeline but never assigned: "
        f"{sorted(missing)}"
    )


def test_laclaudian_categories_are_not_left_to_the_generic_lists() -> None:
    """Issue #108: typed categories must reach their own fields.

    Equivalence/difference chains and floating/empty signifier candidates are
    distinct Laclaudian categories. Folding them into generic `relations` /
    `signifiers` erases the distinction, so assert the dedicated projections
    exist rather than only the collapsed ones.
    """
    written = _written_fields()
    for field in (
        "equivalence_chains",
        "difference_chains",
        "floating_signifiers",
        "empty_signifier_candidates",
    ):
        assert field in written, f"{field} must be projected to its own field"
        assert field in PROJECTED_BY_CANONICAL_PIPELINE


def test_projection_helpers_are_used_for_chains_and_signifiers() -> None:
    """The dedicated fields are filled by the shared helpers, not ad-hoc code."""
    text = PIPELINE.read_text(encoding="utf-8")
    assert "_relation_chains(" in text
    assert '"floating_signifier"' in text
    assert '"empty_signifier"' in text


def test_relation_chains_require_two_members() -> None:
    """A single self-referencing edge is not a chain."""
    import sys

    sys.path.insert(0, str(REPO / "src"))
    from laclaugpt_data_analysis.canonical import CanonicalRecord
    from laclaugpt_data_analysis.canonical_pipeline import (
        DiscursiveRelation,
        _relation_chains,
    )

    record = CanonicalRecord(source_url="https://example.invalid/a")
    relations = [
        DiscursiveRelation(relation_type="equivalence", source="x", target="y"),
        DiscursiveRelation(relation_type="equivalence", source="z", target="z"),
        DiscursiveRelation(relation_type="equivalence", source="", target="w"),
    ]

    chains = _relation_chains(record, relations, "equivalence")

    # Only the first has two distinct members.
    assert len(chains) == 1
    assert chains[0].member_refs == ["x", "y"]
    assert chains[0].chain_type == "equivalence"
    assert chains[0].review_status == "PROVISIONAL"


def test_relation_chain_ids_are_sequential_and_typed() -> None:
    import sys

    sys.path.insert(0, str(REPO / "src"))
    from laclaugpt_data_analysis.canonical import CanonicalRecord
    from laclaugpt_data_analysis.canonical_pipeline import (
        DiscursiveRelation,
        _relation_chains,
    )

    record = CanonicalRecord(source_url="https://example.invalid/a")
    relations = [
        DiscursiveRelation(relation_type="difference", source="a", target="b"),
        DiscursiveRelation(relation_type="difference", source="c", target="d"),
    ]

    chains = _relation_chains(record, relations, "difference")

    assert [c.chain_id for c in chains] == ["difference_chain:1", "difference_chain:2"]
    assert all(c.chain_type == "difference" for c in chains)


def test_empty_proposal_produces_empty_fields_not_errors() -> None:
    """Absence of candidates must stay an empty list, not a failure."""
    import sys

    sys.path.insert(0, str(REPO / "src"))
    from laclaugpt_data_analysis.canonical import CanonicalRecord
    from laclaugpt_data_analysis.canonical_pipeline import _relation_chains

    record = CanonicalRecord(source_url="https://example.invalid/a")
    assert _relation_chains(record, [], "equivalence") == []
