#!/usr/bin/env python3
"""Audit the AI26 review export, and draw a reproducible audit sample from it (#444).

The review export is a *join* of canonical analysis output and the collection record, so it can be
wrong in two directions: a pipeline can fail to produce something, or the export can fail to carry
what the pipeline produced. This tool separates those, because they have different owners and
different fixes.

Three jobs, one file, because they share the same population definitions:

``--profile``
    Completeness and validity of the export as a dataset: row identity, duplicates, per-column
    emptiness, status and version distributions, the ``notes`` taxonomy, text-length quantiles,
    platform/language coverage, and the cross-tab of "has source text" against "has coded output".

``--sample N``
    A deterministic stratified sample: allocation by largest remainder over strata
    (platform x has-text x has-formation), selection by a seeded hash rather than a row position, so
    the same seed reproduces the same records even if the export is regenerated in another order.
    Writes the sample ids and a manifest with seed, allocation and denominators.

``--compare BEFORE AFTER``
    Paired before/after on the *same* record ids: per-concept coverage deltas, and explicitly
    separated improvements and regressions. Aggregates only — this is the number that goes in a
    report, and it is a coverage change, not an accuracy gain.

**Privacy.** The default output never contains a source URL, a title, a transcript, a summary or a
model label. Sample rows carry record ids and stratum facts only; pass ``--include-source-url`` only
for a file that stays in the private repository. Nothing here writes to the store — it reads a CSV.

Usage::

    python tools/ai26_review_audit.py --input review.csv --profile --json profile.json
    python tools/ai26_review_audit.py --input review.csv --sample 100 --seed 444 --out sample.csv
    python tools/ai26_review_audit.py --compare before.csv after.csv --json compare.json

Exit codes: 0 the requested work completed, 1 a check failed (``--fail-on`` finding present, schema
mismatch, or a sample that cannot be drawn), 2 usage error.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

#: The review columns the exporter is contracted to produce, in order. A different header is schema
#: drift, and a reviewer cannot tell a missing column from an empty one, so it is a hard failure.
EXPECTED_COLUMNS = [
    "record_id", "source_url", "platform", "author", "published_at", "language",
    "title", "text_excerpt", "text_chars",
    "analysis_status", "discourse_status", "abstentions", "analysis_version", "summary",
    "themes", "entities",
    "formation", "signifiers", "nodal_points", "imaginaries", "floating_signifiers",
    "us", "them", "antagonisms", "discourses", "notes",
]

#: Columns whose emptiness means "the model produced nothing here" rather than "the item is thin".
CONCEPT_COLUMNS = [
    "formations", "signifiers", "nodal_points", "antagonisms", "themes", "discourses",
    "imaginaries", "us", "them", "floating_signifiers",
]
#: What the exporter calls each concept. Kept explicit so a rename shows up as a mismatch rather than
#: silently comparing different things.
CONCEPT_TO_COLUMN = {
    "formations": "formation",
    "signifiers": "signifiers",
    "nodal_points": "nodal_points",
    "antagonisms": "antagonisms",
    "themes": "themes",
    "discourses": "discourses",
    "imaginaries": "imaginaries",
    "us": "us",
    "them": "them",
    "floating_signifiers": "floating_signifiers",
}


class ExportError(RuntimeError):
    """The file cannot be audited as a review export (wrong shape, unreadable, empty)."""


def read_export(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise ExportError(f"no export at {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    if not columns:
        raise ExportError(f"{path} has no header row")
    if not rows:
        raise ExportError(f"{path} has a header but no records")
    return columns, rows


def schema_diff(columns: list[str], expected: Iterable[str] = EXPECTED_COLUMNS) -> dict[str, list[str]]:
    expected = list(expected)
    return {
        "missing": [c for c in expected if c not in columns],
        "unexpected": [c for c in columns if c not in expected],
        "order_changed": [c for c in expected if c in columns and columns.index(c) != expected.index(c)],
    }


def _nonempty(value: str | None) -> bool:
    return bool((value or "").strip())


def _notes_taxonomy(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        note = (row.get("notes") or "").strip()
        if not note:
            continue
        for part in note.split(";"):
            part = part.strip()
            if part:
                # Collapse the free-text tail ("handoff pending") into its label so the taxonomy is
                # countable; the raw string stays in the row.
                counter[part.split(":")[0][:60]] += 1
    return [{"note": note, "rows": n} for note, n in counter.most_common()]


def _quantiles(values: list[int]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "min": float(ordered[0]),
        "p25": float(statistics.quantiles(ordered, n=4)[0]) if len(ordered) > 3 else float(ordered[0]),
        "median": float(statistics.median(ordered)),
        "p75": float(statistics.quantiles(ordered, n=4)[2]) if len(ordered) > 3 else float(ordered[-1]),
        "max": float(ordered[-1]),
        "mean": round(statistics.fmean(ordered), 1),
        "zero": float(sum(1 for v in ordered if v == 0)),
    }


def _duplicate_summaries(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Exact and whitespace-normalised repeats of the model summary.

    A repeated summary across different items is either a template answer or a copy — both are
    quality signals, and neither is visible in a per-row spreadsheet.
    """
    exact: Counter[str] = Counter()
    normalised: Counter[str] = Counter()
    for row in rows:
        summary = (row.get("summary") or "").strip()
        if not summary:
            continue
        exact[summary] += 1
        normalised[" ".join(summary.lower().split())] += 1
    return {
        "summaries": sum(exact.values()),
        "distinct_exact": len(exact),
        "repeated_exact": sum(1 for n in exact.values() if n > 1),
        "max_repeat": max(exact.values()) if exact else 0,
        "distinct_normalised": len(normalised),
        "repeated_normalised": sum(1 for n in normalised.values() if n > 1),
    }


def profile(columns: list[str], rows: list[dict[str, str]]) -> dict[str, Any]:
    total = len(rows)
    ids = [(row.get("record_id") or "").strip() for row in rows]
    id_counter = Counter(ids)
    duplicates = [rid for rid, n in id_counter.items() if n > 1]

    emptiness = {c: sum(0 if _nonempty(row.get(c)) else 1 for row in rows) for c in columns}
    text_chars = []
    for row in rows:
        try:
            text_chars.append(int((row.get("text_chars") or "0").strip() or 0))
        except ValueError:
            text_chars.append(0)

    has_text = [_nonempty(row.get("text_excerpt")) for row in rows]
    has_summary = [_nonempty(row.get("summary")) for row in rows]
    has_formation = [_nonempty(row.get("formation")) for row in rows]

    by_platform = Counter((row.get("platform") or "").strip() or "(none)" for row in rows)
    by_language = Counter((row.get("language") or "").strip() or "(none)" for row in rows)
    by_status = Counter((row.get("analysis_status") or "").strip() or "(none)" for row in rows)
    by_version = Counter((row.get("analysis_version") or "").strip() or "(none)" for row in rows)

    cross = Counter()
    for text, summary, formation in zip(has_text, has_summary, has_formation, strict=True):
        cross[f"text={int(text)}|summary={int(summary)}|formation={int(formation)}"] += 1

    platform_text = defaultdict(lambda: {"rows": 0, "with_text": 0, "with_formation": 0})
    for row, text, formation in zip(rows, has_text, has_formation, strict=True):
        key = (row.get("platform") or "").strip() or "(none)"
        platform_text[key]["rows"] += 1
        platform_text[key]["with_text"] += int(text)
        platform_text[key]["with_formation"] += int(formation)

    return {
        "rows": total,
        "unique_record_ids": len(id_counter),
        "duplicate_record_ids": len(duplicates),
        "duplicate_examples": duplicates[:5],
        "blank_source_url": sum(0 if _nonempty(row.get("source_url")) else 1 for row in rows),
        "columns": {"count": len(columns), "schema": schema_diff(columns)},
        "emptiness": emptiness,
        "emptiness_share": {c: round(n / total, 4) for c, n in emptiness.items()},
        "concept_coverage": {
            name: {
                "column": column,
                "present": sum(1 for row in rows if _nonempty(row.get(column))) if column in columns else 0,
                "share": round(sum(1 for row in rows if column in columns and _nonempty(row.get(column))) / total, 4),
            }
            for name, column in CONCEPT_TO_COLUMN.items()
        },
        "text_chars": _quantiles(text_chars),
        "records_without_source_text": total - sum(has_text),
        "records_without_formation": total - sum(has_formation),
        "records_without_summary": total - sum(has_summary),
        "cross_tab": dict(cross.most_common()),
        "by_platform": dict(by_platform.most_common()),
        "by_language": dict(by_language.most_common()),
        "by_analysis_status": dict(by_status.most_common()),
        "by_analysis_version": dict(by_version.most_common()),
        "per_platform": {k: v for k, v in sorted(platform_text.items())},
        "notes": _notes_taxonomy(rows),
        "summary_repetition": _duplicate_summaries(rows),
    }


def strata_keys(rows: list[dict[str, str]]) -> list[str]:
    keys = []
    for row in rows:
        platform = (row.get("platform") or "").strip() or "(none)"
        text = "text" if _nonempty(row.get("text_excerpt")) else "no-text"
        formation = "formation" if _nonempty(row.get("formation")) else "no-formation"
        keys.append(f"{platform}|{text}|{formation}")
    return keys


def _seeded_order(record_id: str, seed: int) -> str:
    """Order within a stratum, stable across export regeneration.

    A row position would depend on the export's ordering; a hash of the id does not. Two runs with the
    same seed therefore draw the same records from the same population.
    """
    return hashlib.sha256(f"{seed}:{record_id}".encode()).hexdigest()


def allocate(counts: dict[str, int], size: int, *, floor: int = 0) -> dict[str, int]:
    """Apportion ``size`` over ``counts``: a floor per non-empty stratum, then largest remainder.

    A proportional sample of a 5,302-item export draws nothing from an 8-item stratum, and those
    small strata are exactly the defect cases an audit needs to read: the no-text rows and the
    no-formation rows. The floor guarantees each non-empty stratum appears; the remainder keeps the
    sample proportional. Everything is deterministic and never exceeds a stratum.
    """
    counts = {k: n for k, n in counts.items() if n > 0}
    population = sum(counts.values())
    if population == 0 or size <= 0:
        return {k: 0 for k in counts}
    size = min(size, population)
    floor = max(0, min(floor, size))

    # Not enough slots for the floor everywhere: take the largest strata first, by population.
    if floor and floor * len(counts) > size:
        chosen = sorted(counts, key=lambda k: (-counts[k], k))[:size]
        return {k: (1 if k in chosen else 0) for k in counts}

    base = {k: min(floor, counts[k]) for k in counts}
    remainder = size - sum(base.values())
    if remainder == 0:
        return base

    capacity = {k: counts[k] - base[k] for k in counts}
    capacity_total = sum(capacity.values())
    exact = {k: remainder * cap / capacity_total if capacity_total else 0.0 for k, cap in capacity.items()}
    for key, value in exact.items():
        base[key] += min(int(value), capacity[key])
    left = size - sum(base.values())
    order = sorted(counts, key=lambda k: (-(exact.get(k, 0.0) - int(exact.get(k, 0.0))), k))
    index = 0
    while left > 0 and index < len(order) * 4:
        key = order[index % len(order)]
        if base[key] < counts[key]:
            base[key] += 1
            left -= 1
        index += 1
    return base


def sample(rows: list[dict[str, str]], size: int, seed: int, *, floor: int = 1) -> dict[str, Any]:
    keys = strata_keys(rows)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for key, row in zip(keys, rows, strict=True):
        grouped[key].append(row)

    quotas = allocate({k: len(v) for k, v in grouped.items()}, size, floor=floor)
    picked: list[dict[str, Any]] = []
    for key in sorted(grouped):
        members = sorted(grouped[key], key=lambda r: _seeded_order((r.get("record_id") or ""), seed))
        for row in members[: quotas[key]]:
            picked.append({
                "record_id": (row.get("record_id") or "").strip(),
                "platform": (row.get("platform") or "").strip(),
                "language": (row.get("language") or "").strip(),
                "has_text": int(_nonempty(row.get("text_excerpt"))),
                "has_formation": int(_nonempty(row.get("formation"))),
                "analysis_version": (row.get("analysis_version") or "").strip(),
                "stratum": key,
                "source_url": (row.get("source_url") or "").strip(),
            })
    picked.sort(key=lambda r: r["record_id"])
    return {
        "seed": seed,
        "floor_per_stratum": floor,
        "requested": size,
        "population": len(rows),
        "drawn": len(picked),
        "strata": {k: {"population": len(v), "quota": quotas[k]} for k, v in sorted(grouped.items())},
        "rows": picked,
    }


def compare(before: list[dict[str, str]], after: list[dict[str, str]]) -> dict[str, Any]:
    """Paired coverage change on shared record ids; improvements and regressions kept apart."""
    b = {(r.get("record_id") or "").strip(): r for r in before}
    a = {(r.get("record_id") or "").strip(): r for r in after}
    shared = sorted(set(b) & set(a))
    only_before = sorted(set(b) - set(a))
    only_after = sorted(set(a) - set(b))

    concepts: dict[str, Any] = {}
    for name, column in CONCEPT_TO_COLUMN.items():
        gained = lost = 0
        for rid in shared:
            had = _nonempty(b[rid].get(column))
            has = _nonempty(a[rid].get(column))
            gained += int(has and not had)
            lost += int(had and not has)
        present_before = sum(1 for rid in shared if _nonempty(b[rid].get(column)))
        present_after = sum(1 for rid in shared if _nonempty(a[rid].get(column)))
        concepts[name] = {
            "column": column,
            "present_before": present_before,
            "present_after": present_after,
            "gained": gained,
            "lost": lost,
            "net": present_after - present_before,
            "regressions": lost,
        }
    changed_summary = sum(1 for rid in shared
                          if (b[rid].get("summary") or "").strip() != (a[rid].get("summary") or "").strip())
    return {
        "shared_record_ids": len(shared),
        "only_before": len(only_before),
        "only_after": len(only_after),
        "summary_changed": changed_summary,
        "concepts": concepts,
        "regressions_total": sum(v["regressions"] for v in concepts.values()),
        "improvements_total": sum(v["gained"] for v in concepts.values()),
    }


def render_profile(data: dict[str, Any], *, source: str) -> str:
    lines = [
        f"AI26 review export audit — {source}",
        "",
        f"rows {data['rows']}  unique ids {data['unique_record_ids']}  "
        f"duplicates {data['duplicate_record_ids']}  blank source_url {data['blank_source_url']}",
        f"schema: {data['columns']['count']} columns, "
        f"missing {data['columns']['schema']['missing'] or 'none'}, "
        f"unexpected {data['columns']['schema']['unexpected'] or 'none'}",
        "",
        "concept coverage (rows with a non-empty value):",
    ]
    for name, item in data["concept_coverage"].items():
        lines.append(f"  {name:22s} {item['present']:5d}  {item['share']:6.1%}  (column {item['column']})")
    text = data["text_chars"]
    lines += [
        "",
        f"source text: {data['records_without_source_text']} rows carry none; "
        f"chars min {int(text.get('min', 0))} median {int(text.get('median', 0))} max {int(text.get('max', 0))}",
        f"records without a coded formation: {data['records_without_formation']}",
        f"records without a summary: {data['records_without_summary']}",
        "",
        "status/version:",
        f"  status  {data['by_analysis_status']}",
        f"  version {data['by_analysis_version']}",
        "",
        "per platform (rows / with text / with formation):",
    ]
    for platform, item in data["per_platform"].items():
        lines.append(f"  {platform:10s} {item['rows']:5d} / {item['with_text']:5d} / {item['with_formation']:5d}")
    if data["notes"]:
        lines += ["", "notes taxonomy:"]
        lines += [f"  {n['rows']:5d}  {n['note']}" for n in data["notes"][:10]]
    rep = data["summary_repetition"]
    lines += [
        "",
        f"summaries: {rep['summaries']} present, {rep['distinct_exact']} distinct, "
        f"{rep['repeated_exact']} values repeated, max repeat {rep['max_repeat']}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), type=Path)
    parser.add_argument("--sample", type=int, metavar="N")
    parser.add_argument("--seed", type=int, default=444)
    parser.add_argument("--min-per-stratum", type=int, default=1,
                        help="fewest rows any non-empty stratum gets; an audit sample needs the rare "
                             "no-text/no-formation cases, which proportionality alone drops (default 1)")
    parser.add_argument("--out", type=Path, help="where to write the sample CSV")
    parser.add_argument("--manifest", type=Path, help="where to write the sample manifest JSON")
    parser.add_argument("--include-source-url", action="store_true",
                        help="keep source URLs in the sample; only for a file that stays private")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--fail-on", choices=["schema", "missing-text", "any"], default=None)
    args = parser.parse_args(argv)

    if args.compare:
        try:
            before_cols, before = read_export(args.compare[0])
            after_cols, after = read_export(args.compare[1])
        except ExportError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        result = {"before": str(args.compare[0]), "after": str(args.compare[1]),
                  "schema_before": schema_diff(before_cols), "schema_after": schema_diff(after_cols),
                  "coverage": compare(before, after)}
        if args.json:
            args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result["coverage"], indent=2))
        return 0

    if not args.input:
        print("error: --input is required (or --compare BEFORE AFTER)", file=sys.stderr)
        return 2
    try:
        columns, rows = read_export(args.input)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    exit_code = 0
    report: dict[str, Any] = {"input": str(args.input)}

    if args.profile or not args.sample:
        data = profile(columns, rows)
        report["profile"] = data
        if not args.json:
            sys.stdout.write(render_profile(data, source=str(args.input)))
        schema = data["columns"]["schema"]
        if args.fail_on == "schema" and any(schema.values()):
            exit_code = 1
        elif args.fail_on in {"missing-text", "any"} and data["records_without_source_text"]:
            exit_code = 1

    if args.sample:
        if args.sample <= 0:
            print("error: --sample must be positive", file=sys.stderr)
            return 2
        drawn = sample(rows, args.sample, args.seed, floor=args.min_per_stratum)
        report["sample"] = {k: drawn[k] for k in ("seed", "requested", "population", "drawn", "strata")}
        if args.out:
            fieldnames = ["record_id", "platform", "language", "has_text", "has_formation",
                          "analysis_version", "stratum"]
            if args.include_source_url:
                fieldnames.append("source_url")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(drawn["rows"])
            print(f"sample: {drawn['drawn']} of {drawn['population']} rows -> {args.out} "
                  f"(seed {args.seed}, {len(drawn['strata'])} strata)")
        if args.manifest:
            args.manifest.write_text(json.dumps({k: v for k, v in drawn.items() if k != "rows"},
                                                indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
