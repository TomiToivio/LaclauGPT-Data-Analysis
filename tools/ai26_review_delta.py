#!/usr/bin/env python3
"""Paired before/after comparison of two AI26 review exports (#444).

This is deliberately the *only* job of this tool. Profiling an export, cross-checking its manifest and
drawing the audit sample are done by ``tools/ai26_review_export_audit.py``; a second profile
implementation would drift from the first, which is exactly what happened when two of these tools were
written in parallel. What no other tool does is compare a **fixed sample** across a change — the step
#444 asks for ("before/after quality comparison on the same documented sample") once prompts or
codebooks are revised.

The comparison is paired on ``record_id`` and reports, per Phase 1 concept, how many records gained a
value, how many lost one, and how many summaries changed. Gains and regressions are kept apart because
a net number hides a regression behind two improvements. Records present on only one side are counted,
never scored.

**Coverage, not accuracy.** A field becoming non-empty says the pipeline produced something; it says
nothing about whether the interpretation is right. Reported that way, on purpose.

Usage::

    python tools/ai26_review_delta.py --before old.csv --after new.csv
    python tools/ai26_review_delta.py --before old.csv --after new.csv --json delta.json

Exit codes: 0 compared, 1 a regression was found and ``--fail-on-regression`` was passed, 2 usage.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

#: Concept name -> column in the review export. Explicit so a rename shows up as a mismatch instead of
#: comparing two different things under one label.
CONCEPT_COLUMNS = {
    "formations": "formations",
    "formation_first": "formation",
    "signifiers": "signifiers",
    "nodal_points": "nodal_points",
    "imaginaries": "imaginaries",
    "floating_signifiers": "floating_signifiers",
    "antagonisms": "antagonisms",
    "equivalences": "equivalences",
    "discourses": "discourses",
    "themes": "themes",
}

#: Columns that identify a row or carry source material; never read for the delta.
IDENTITY_COLUMNS = ("record_id", "source_url")


class ExportError(RuntimeError):
    """The file cannot be read as a review export."""


def read_export(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a review export, allowing cells as large as the full source text.

    ``csv`` refuses fields over 128 kB; the export carries whole texts, so the default limit stops the
    read before it starts. The limit is raised to the largest size Python will accept rather than to a
    guessed number.
    """
    if not path.is_file():
        raise ExportError(f"no export at {path}")
    limit = sys.maxsize
    while limit > 1024:
        try:
            csv.field_size_limit(limit)
            break
        except OverflowError:
            limit //= 2
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or [])
            rows = list(reader)
    except csv.Error as exc:
        raise ExportError(f"{path} is not readable as CSV: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ExportError(f"{path} is not UTF-8: {exc}") from exc
    if not columns:
        raise ExportError(f"{path} has no header row")
    if not rows:
        raise ExportError(f"{path} has a header but no records")
    return columns, rows


def _present(value: str | None) -> bool:
    return bool((value or "").strip())


def compare(before: list[dict[str, str]], after: list[dict[str, str]], *,
            columns: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Paired delta over shared record ids; regressions counted separately from gains."""
    key = "record_id"
    b = {(row.get(key) or "").strip(): row for row in before}
    a = {(row.get(key) or "").strip(): row for row in after}
    shared = sorted(set(b) & set(a))

    concepts: dict[str, Any] = {}
    for name, column in CONCEPT_COLUMNS.items():
        if columns is not None and column not in columns:
            concepts[name] = {"column": column, "absent": True}
            continue
        gained = lost = 0
        for rid in shared:
            had, has = _present(b[rid].get(column)), _present(a[rid].get(column))
            gained += int(has and not had)
            lost += int(had and not has)
        present_before = sum(1 for rid in shared if _present(b[rid].get(column)))
        present_after = sum(1 for rid in shared if _present(a[rid].get(column)))
        concepts[name] = {
            "column": column,
            "present_before": present_before,
            "present_after": present_after,
            "gained": gained,
            "lost": lost,
            "net": present_after - present_before,
        }

    summary_changed = sum(
        1 for rid in shared
        if (b[rid].get("analysis_summary") or b[rid].get("summary") or "").strip()
        != (a[rid].get("analysis_summary") or a[rid].get("summary") or "").strip()
    )
    return {
        "shared_record_ids": len(shared),
        "only_before": len(set(b) - set(a)),
        "only_after": len(set(a) - set(b)),
        "summary_changed": summary_changed,
        "concepts": concepts,
        "improvements_total": sum(v.get("gained", 0) for v in concepts.values()),
        "regressions_total": sum(v.get("lost", 0) for v in concepts.values()),
    }


def render(delta: dict[str, Any], *, before: str, after: str) -> str:
    lines = [
        f"AI26 review export delta — {before} -> {after}",
        "",
        f"shared record ids {delta['shared_record_ids']}  "
        f"only before {delta['only_before']}  only after {delta['only_after']}",
        f"summaries changed: {delta['summary_changed']}",
        "",
        f"{'concept':22s} {'before':>8s} {'after':>8s} {'gained':>8s} {'lost':>8s} {'net':>8s}",
    ]
    for name, item in delta["concepts"].items():
        if item.get("absent"):
            lines.append(f"{name:22s} {'—':>8s} {'—':>8s} {'—':>8s} {'—':>8s} {'absent':>8s}")
            continue
        lines.append(f"{name:22s} {item['present_before']:8d} {item['present_after']:8d} "
                     f"{item['gained']:8d} {item['lost']:8d} {item['net']:8d}")
    lines += ["", f"improvements {delta['improvements_total']}  regressions {delta['regressions_total']}",
              "Coverage changed; accuracy is not measured here."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--fail-on-regression", action="store_true",
                        help="exit 1 when any concept lost a value on a shared record")
    args = parser.parse_args(argv)

    try:
        before_columns, before = read_export(args.before)
        after_columns, after = read_export(args.after)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    columns = tuple(c for c in after_columns if c in before_columns)
    delta = compare(before, after, columns=columns)
    if args.json:
        args.json.write_text(json.dumps({"before": str(args.before), "after": str(args.after),
                                         "columns_shared": list(columns), "delta": delta},
                                        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(render(delta, before=str(args.before), after=str(args.after)))
    if args.fail_on_regression and delta["regressions_total"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
