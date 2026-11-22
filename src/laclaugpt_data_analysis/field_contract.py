"""Which analysis fields the pipeline actually produces, checked against the schema (#450, #452, #453).

A field can be declared on `AnalysisSection`, exported to RDF and the knowledge graph, asked for in the
prompt, and still have no path from the model's answer to the record. Three such fields were found by
reading the live corpus: `themes` (#453), `discourses` (#450) and `them` (#452). Each looked identical
to a working field from the outside — the column existed and was empty — and each took a separate
investigation to diagnose.

This module makes that class of defect a failing test instead of a discovery:

* it scans the package for assignments to an analysis field (`record.analysis.<field> = …`,
  `.append(…)`, `analysis["<field>"] = …`);
* it compares that set with the fields `AnalysisSection` declares;
* a field in the schema with no producer must be **registered** here with the issue that tracks it and
  the decision it needs — so "we know, and here is why it is still empty" is recorded once, in code.

Registering a field is deliberately not a way to silence the check for a working field: a registered
field that does have a producer fails the test as stale.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

#: The package the scan reads. Kept as data so tests can point it at a fixture tree.
DEFAULT_PACKAGE = Path(__file__).resolve().parent


#: How a declared field ends up empty, which decides who fixes it.
NO_PRODUCER = "no-producer"
PRODUCER_WITHOUT_INPUT = "producer-without-input"
PRODUCER_MISSING_UPSTREAM = "producer-missing-upstream"


@dataclass(frozen=True)
class UnproducedField:
    """A schema field that is empty in the corpus, and what has to happen before it is not."""

    field: str
    issue: str
    defect: str
    reason: str
    decision: str


#: Fields declared on `AnalysisSection` that nothing assigns. Adding an entry is a claim that the field
#: is knowingly empty; removing one is a claim that a producer now exists. Both are checked.
UNPRODUCED_FIELDS: dict[str, UnproducedField] = {
    "us": UnproducedField(
        field="us",
        issue="#452",
        defect=NO_PRODUCER,
        reason="the pipeline wrote `us` from the same collective subjects it now stores under the "
               "codebook's own name; nothing produces `us` after the ruling",
        decision="RETIRED for Phase 1: kept as a read-only legacy alias (lifted into "
                 "collective_subjects on load) so historical records still project",
    ),
    "them": UnproducedField(
        field="them",
        issue="#452",
        defect=NO_PRODUCER,
        reason="postprocess wrote us from collective_subjects and nothing wrote them; "
               "stage_contract does not declare it either, so the us/them pair is half-populated by "
               "construction",
        decision="RETIRED for Phase 1: the codebook codes collective_subjects and the opposed pole is "
                 "an antagonism target_ref. New records write collective_subjects; the legacy us/them "
                 "fields stay declared only so historical records load and project",
    ),
    "topic_assignments": UnproducedField(
        field="topic_assignments",
        issue="#444",
        defect=NO_PRODUCER,
        reason="topics are produced but per-document assignments are not, so the pair cannot support a "
               "per-document analysis",
        decision="emit assignments alongside topics, or retire the field and its exporters",
    ),
    "embeddings": UnproducedField(
        field="embeddings",
        issue="#444",
        defect=NO_PRODUCER,
        reason="declared and exported, assigned nowhere outside the vendored EP24 pipeline, so it is "
               "empty for every AI26 record",
        decision="produce embeddings in the AI26 analysis path, or retire the field from the record "
                 "and its exporters",
    ),
    "representations": UnproducedField(
        field="representations",
        issue="#444",
        defect=NO_PRODUCER,
        reason="same shape as embeddings: declared, exported, never assigned by the AI26 path",
        decision="produce representations where the multimodal stages run, or retire the field and "
                 "stop exporting it",
    ),
    "entity_mentions": UnproducedField(
        field="entity_mentions",
        issue="#444",
        defect=NO_PRODUCER,
        reason="entities are stored with ids but no mention spans, so nothing links a label to where "
               "it occurred in the source",
        decision="emit mention spans when entities are extracted, or retire the field",
    ),
    "discourses": UnproducedField(
        field="discourses",
        issue="#450",
        defect=PRODUCER_MISSING_UPSTREAM,
        reason="AnalysisProposal declares discourses and pipeline.py copies it, but the discourse "
               "stage returns DiscourseProposal, which has no discourses field — so the copy is always "
               "an empty list",
        decision="RETIRED 2026-11-22 (D1, docs/AI26_OPEN_DECISIONS.md): no discourse level exists in "
                 "the Phase 1 vocabulary and none is computed, so the review export no longer carries "
                 "the column. The storage field stays reserved for Phase 2 rather than breaking 5 302 "
                 "stored records; a phase that produces discourses fills it and re-enables the column.",
    ),
    "themes": UnproducedField(
        field="themes",
        issue="#453",
        defect=PRODUCER_WITHOUT_INPUT,
        reason="pipeline.py assigns themes from proposal.themes and the prompt asks for them, but the "
               "analysed corpus carries none: the path that ran is the discourse stage, whose "
               "DiscourseProposal has no themes field",
        decision="RETIRED FROM THE PROMPT 2026-11-22 (D3, docs/AI26_OPEN_DECISIONS.md): the prompt no "
                 "longer asks for themes, because a field the schema discards spends tokens on text that "
                 "is thrown away. Kept reserved in the record until a decision names what a theme is "
                 "that `topics` does not already capture.",
    ),
}


def analysis_fields() -> tuple[str, ...]:
    """The fields `AnalysisSection` declares, in declaration order."""
    from .canonical import AnalysisSection

    return tuple(AnalysisSection.model_fields)


def produced_fields(package: Path = DEFAULT_PACKAGE) -> dict[str, list[str]]:
    """Field name -> files that assign it, found by AST rather than by grep.

    Three shapes count as production, because the package uses all three: attribute assignment
    (`record.analysis.formations = …`), mutation (`record.analysis.model_runs.append(…)`) and
    dict-style assignment in the version adapters (`analysis["codebook_refs"] = …`). A read is not a
    producer, which is why the scan looks at assignment targets only.
    """
    produced: dict[str, list[str]] = {}

    for path in sorted(package.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # a broken file is somebody else's test's problem
            continue
        for node in ast.walk(tree):
            name = _target_field(node)
            if name:
                produced.setdefault(name, []).append(str(path.relative_to(package)))
    return produced


def _target_field(node: ast.AST) -> str | None:
    """The analysis field an assignment or call mutates, if it is one."""
    if isinstance(node, ast.Assign):
        for target in node.targets:
            found = _attribute_chain(target)
            if found:
                return found
        return None
    if isinstance(node, ast.AugAssign):
        return _attribute_chain(node.target)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {"append", "extend", "insert"}:
            return _attribute_chain(func.value)
    return None


def _attribute_chain(node: ast.AST) -> str | None:
    """`x.analysis.<field>` or `x["<field>"]` -> `<field>`; anything else -> None."""
    if isinstance(node, ast.Attribute):
        value = node.value
        if isinstance(value, ast.Attribute) and value.attr == "analysis":
            return node.attr
        return None
    if isinstance(node, ast.Subscript):
        value = node.value
        # record.analysis.plugin_results["rdf"] = ... writes the field through a keyed container.
        if isinstance(value, ast.Attribute):
            inner = _attribute_chain(value)
            if inner:
                return inner
        is_analysis = (
            (isinstance(value, ast.Attribute) and value.attr == "analysis")
            or (isinstance(value, ast.Name) and value.id == "analysis")
        )
        if not is_analysis:
            return None
        key = node.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return key.value
    return None


def contract() -> dict[str, list[str]]:
    """Disagreements between the schema, the producers and the registry.

    Keys are stable so a test can assert on them: `unregistered` (schema field, no producer, not
    registered), `stale` (registered, but something produces it), and `unknown` (registered field that
    the schema does not declare).
    """
    fields = set(analysis_fields())
    produced = set(produced_fields())
    registered = set(UNPRODUCED_FIELDS)

    no_producer = {name for name, entry in UNPRODUCED_FIELDS.items() if entry.defect == NO_PRODUCER}
    return {
        "unregistered": sorted(fields - produced - registered),
        # Only a field claimed to have *no* producer can be contradicted by the scan; the other
        # classes are produced and empty for a reason the scan cannot see.
        "stale": sorted(no_producer & produced),
        "unknown": sorted(registered - fields),
        "produced": sorted(fields & produced),
        "registered_empty": sorted((fields - produced) & registered),
    }


def describe() -> str:
    """A one-screen summary, for a person rather than a test."""
    report = contract()
    lines = [
        f"analysis fields declared: {len(analysis_fields())}",
        f"  produced:            {len(report['produced'])}",
        f"  registered empty:    {len(report['registered_empty'])}",
        "",
    ]
    # Every registered field is listed with its class, including the ones that are assigned but
    # empty in the corpus: hiding those would make the registry read as "all fixed".
    for field in sorted(UNPRODUCED_FIELDS):
        entry = UNPRODUCED_FIELDS[field]
        lines.append(f"  {field:20s} {entry.issue:6s} {entry.defect:26s} {entry.reason[:70]}")
    if report["unregistered"]:
        lines.append("")
        lines.append("UNREGISTERED — declared, never assigned, not registered:")
        lines += [f"  {field}" for field in report["unregistered"]]
    if report["stale"]:
        lines.append("")
        lines.append("STALE — registered as empty but something assigns it:")
        lines += [f"  {field}" for field in report["stale"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    import sys

    sys.stdout.write(describe())
    report = contract()
    return 1 if (report["unregistered"] or report["stale"] or report["unknown"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
