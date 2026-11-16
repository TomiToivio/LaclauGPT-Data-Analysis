"""Issue #450 / #452 / #453: a canonical analysis field must have a producer or be declared reserved.

The AI26 audit found three fields that exist in `AnalysisSection`, are exported to reviewers, and
are assigned nowhere: `themes`, `discourses` and `them` (and `equivalences`/`codebook_refs` in the
same family). That is invisible in CI — a field with no producer is not a failing test, it is a
silently empty column that a reader mistakes for a model failure.

This test makes the gap explicit and ratchets it:

* every field of `AnalysisSection` must either be assigned somewhere in the package, or be listed in
  `RESERVED_WITHOUT_PRODUCER` together with the issue that tracks the decision;
* when a field **gains** a producer, the test fails until it is removed from the registry — so the
  registry cannot drift into a stale list of "known gaps" that no longer exist.

It asserts nothing about the science. Whether `them` should be coded, or `discourses` retired, is the
decision recorded in the issue each entry names.
"""
from __future__ import annotations

import re
from pathlib import Path

from laclaugpt_data_analysis.canonical import AnalysisSection

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "laclaugpt_data_analysis"

#: Field -> the issue where its missing producer is being decided.
#: This registry is for fields with **no assignment anywhere in the package**. Fields that are
#: assigned but never populated in practice (`themes`, `codebook_refs` in the AI26 corpus) are a
#: different and harder question — an assignment exists, so a static test cannot call it a gap.
#: Add an entry only with an issue number, and remove it as soon as a producer exists.
RESERVED_WITHOUT_PRODUCER = {
    "discourses": "#450 — no stage returns it; produce or retire",
    "them": "#452 — `us` is written from collective_subjects, `them` is written nowhere",
}

#: Fields whose producer is the framework rather than a stage (timestamps, status, containers
#: filled by appenders, sinks or the multimodal preprocessor rather than by a direct assignment).
FRAMEWORK_FIELDS = {
    "status", "started_at", "completed_at", "uncertainty", "abstentions", "model_runs",
    "plugin_results", "plugin_failures", "memory_refs", "representations", "embeddings",
    "entity_mentions", "topic_assignments",
}


def _assigned_fields() -> set[str]:
    """Fields assigned anywhere in the package as `analysis.<field> = …` or `record.analysis.<field> = …`."""
    pattern = re.compile(r"(?:\banalysis|\brecord\.analysis)\.([a-z_]+)\s*(?::[^=\n]+)?=")
    assigned: set[str] = set()
    for path in PACKAGE.rglob("*.py"):
        for match in pattern.finditer(path.read_text(encoding="utf-8", errors="replace")):
            assigned.add(match.group(1))
    return assigned


def test_registry_entries_are_still_real_gaps():
    """A field that gained a producer must leave the registry, or the registry lies."""
    assigned = _assigned_fields()
    stale = {field: issue for field, issue in RESERVED_WITHOUT_PRODUCER.items() if field in assigned}
    assert not stale, (
        "These fields now have a producer, so remove them from RESERVED_WITHOUT_PRODUCER "
        f"(and close the issue if that was the decision): {stale}"
    )


def test_every_unproduced_field_is_declared_with_an_issue():
    """No canonical field may be silently unproduced: it is either assigned or declared."""
    assigned = _assigned_fields()
    declared = set(RESERVED_WITHOUT_PRODUCER) | FRAMEWORK_FIELDS
    silent = {
        field for field in AnalysisSection.model_fields
        if field not in assigned and field not in declared
    }
    assert not silent, (
        "AnalysisSection fields with no producer and no tracked decision: "
        f"{sorted(silent)}. Either assign the field or add it to RESERVED_WITHOUT_PRODUCER "
        "with the issue that decides it."
    )


def test_registry_only_names_known_canonical_fields():
    unknown = set(RESERVED_WITHOUT_PRODUCER) - set(AnalysisSection.model_fields)
    assert not unknown, f"RESERVED_WITHOUT_PRODUCER names fields that do not exist: {sorted(unknown)}"


def test_registry_names_do_not_include_framework_fields():
    overlap = set(RESERVED_WITHOUT_PRODUCER) & FRAMEWORK_FIELDS
    assert not overlap, (
        f"{sorted(overlap)} is declared both framework-produced and unproduced; pick one"
    )
