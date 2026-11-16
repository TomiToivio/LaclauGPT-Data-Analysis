#!/usr/bin/env python3
"""Read-only diagnostics over the AI26 review export (#449, #451, #454, #458, #460).

Five issues in this batch are the same kind of question: *what does the corpus actually contain, and
where does it not support what the pipeline produced?* They were each being measured by hand, with a
snippet in an issue comment. This tool does all five measurements from one file, reproducibly, and
prints aggregates only.

    --markup             how much HTML/CSS/JS sits inside `source_text`, by platform, and how often the
                         200,000-character cap is hit (#449)
    --coverage-by-length coded-field coverage per source-text-length bucket, including the zero-text
                         stratum that should not be coded at all (#451, #460)
    --formations         how `formations[0]` labels are built: machine tokens vs prose, and how much of
                         the corpus one label covers (#454)
    --evidence           how many citations the pipeline attached and how many it could locate verbatim
                         in the source (#458)
    --fields             per-column non-empty counts, flagging any column empty in every row (#450, #452,
                         #453)

**Privacy:** counts, bucket labels, platform names and character lengths only. No URL, title, summary,
quote or source text is printed, and the report can be pasted into a public issue.

Usage::

    python tools/ai26_corpus_diagnostics.py --input review.csv --all
    python tools/ai26_corpus_diagnostics.py --input review.csv --markup --coverage-by-length
    python tools/ai26_corpus_diagnostics.py --input review.csv --all --json diagnostics.json

Exit codes: 0 measured, 2 the file cannot be read.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

#: Text-length buckets, in characters. The first is the one that matters most: text the pipeline never
#: had, which is still coded at 96% (#460).
LENGTH_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("0", 0, 0),
    ("1-60", 1, 60),
    ("61-150", 61, 150),
    ("151-300", 151, 300),
    ("301-800", 301, 800),
    ("801-3000", 801, 3000),
    ("3001+", 3001, None),
)
#: The upload cap the analysis truncates at. A row sitting exactly here lost text (#449).
TRUNCATION_CAP = 200_000

MARKUP_TAG = re.compile(r"<[a-zA-Z/][^>]{0,200}>")
CSS_CUSTOM_PROPERTY = re.compile(r"--[a-z][a-z0-9-]{2,}\s*:")
SCRIPT_BLOB = re.compile(r"(?:function\s*\(|=>\s*\{|var\s+\w+\s*=|window\.\w+\s*=)")

MACHINE_LABEL = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


class ExportError(RuntimeError):
    pass


def read_export(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise ExportError(f"no export at {path}")
    limit = sys.maxsize
    while limit > 1024:  # cells are whole documents; csv's default 128 kB is far too small
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
    if not columns or not rows:
        raise ExportError(f"{path} has no header or no records")
    return columns, rows


def _text(row: dict[str, str]) -> str:
    return row.get("source_text") or row.get("text_excerpt") or ""


def _chars(row: dict[str, str]) -> int:
    raw = (row.get("text_chars") or "").strip()
    if raw.isdigit():
        return int(raw)
    return len(_text(row))


def markup(rows: list[dict[str, str]]) -> dict[str, Any]:
    """How much of the stored text is not prose (#449)."""
    per_platform: dict[str, dict[str, int]] = defaultdict(
        lambda: {"rows": 0, "with_markup": 0, "with_css": 0, "with_script": 0, "at_cap": 0,
                 "markup_chars": 0, "total_chars": 0})
    totals = Counter()
    for row in rows:
        text = _text(row)
        platform = (row.get("platform") or "").strip() or "(none)"
        entry = per_platform[platform]
        entry["rows"] += 1
        entry["total_chars"] += len(text)
        has_markup = bool(MARKUP_TAG.search(text))
        has_css = bool(CSS_CUSTOM_PROPERTY.search(text))
        has_script = bool(SCRIPT_BLOB.search(text))
        entry["with_markup"] += int(has_markup)
        entry["with_css"] += int(has_css)
        entry["with_script"] += int(has_script)
        entry["at_cap"] += int(len(text) >= TRUNCATION_CAP or _chars(row) >= TRUNCATION_CAP)
        if has_markup or has_css or has_script:
            totals["rows_with_any"] += 1
        # A crude but honest share: the characters inside tags, not a readability estimate.
        entry["markup_chars"] += sum(len(m.group(0)) for m in MARKUP_TAG.finditer(text))
    for entry in per_platform.values():
        entry["markup_share"] = round(entry["markup_chars"] / entry["total_chars"], 4) if entry["total_chars"] else 0.0
    return {
        "rows": len(rows),
        "rows_with_any_markup": totals["rows_with_any"],
        "share_with_any_markup": round(totals["rows_with_any"] / len(rows), 4) if rows else 0.0,
        "rows_at_truncation_cap": sum(1 for row in rows if _chars(row) >= TRUNCATION_CAP),
        "per_platform": {k: v for k, v in sorted(per_platform.items())},
    }


def _bucket(chars: int) -> str:
    for name, low, high in LENGTH_BUCKETS:
        if chars >= low and (high is None or chars <= high):
            return name
    return LENGTH_BUCKETS[-1][0]


def coverage_by_length(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Coded-field coverage per source-text length (#460), with the zero-text stratum called out."""
    concepts = {"formations": "formations", "signifiers": "signifiers", "antagonisms": "antagonisms"}
    buckets: dict[str, dict[str, Any]] = {}
    for name, _, _ in LENGTH_BUCKETS:
        buckets[name] = {"rows": 0, **{f"{c}_coded": 0 for c in concepts}}

    for row in rows:
        bucket = buckets[_bucket(_chars(row))]
        bucket["rows"] += 1
        for concept, column in concepts.items():
            # `formations` is a list rendered as a string; `formation` is its first label.
            value = row.get(column) or (row.get("formation") if concept == "formations" else "")
            bucket[f"{concept}_coded"] += int(bool((value or "").strip()))

    for bucket in buckets.values():
        n = bucket["rows"]
        bucket["shares"] = {
            c: (round(bucket[f"{c}_coded"] / n, 3) if n else 0.0) for c in concepts
        }
    zero = buckets["0"]
    return {
        "rows": len(rows),
        "buckets": buckets,
        "zero_text": {
            "rows": zero["rows"],
            "formation_share": zero["shares"]["formations"] if zero["rows"] else 0.0,
            "signifier_share": zero["shares"]["signifiers"] if zero["rows"] else 0.0,
            "antagonism_share": zero["shares"]["antagonisms"] if zero["rows"] else 0.0,
        },
    }


def formations(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Label grammars and label concentration (#454)."""
    labels: list[str] = []
    for row in rows:
        raw = (row.get("formations") or row.get("formation") or "").strip()
        if not raw:
            continue
        # The export renders a list as `a; b`; the first label is the one the issue measured.
        labels.append(raw.split(";")[0].strip())
    machine = [label for label in labels if MACHINE_LABEL.match(label)]
    prose = [label for label in labels if label and not MACHINE_LABEL.match(label)]
    counter = Counter(labels)
    top = counter.most_common(5)
    return {
        "rows": len(rows),
        "with_label": len(labels),
        "distinct_labels": len(counter),
        "machine_token_labels": len(machine),
        "prose_labels": len(prose),
        "machine_share": round(len(machine) / len(labels), 4) if labels else 0.0,
        "top_label_share": round(top[0][1] / len(labels), 4) if labels else 0.0,
        "top_labels": [{"label_length": len(label), "rows": count} for label, count in top],
        "singleton_labels": sum(1 for count in counter.values() if count == 1),
    }


def evidence(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Citation volume and how much of it resolves verbatim (#458)."""
    columns = {"evidence_count", "evidence_exact_count"}
    if not columns <= set(rows[0] if rows else {}):
        return {"available": False,
                "reason": "the export has no evidence_count/evidence_exact_count columns; "
                          "regenerate it with the current exporter"}
    total = exact = 0
    rows_without_citation = rows_all_verbatim = rows_any_verbatim = 0
    for row in rows:
        try:
            count = int((row.get("evidence_count") or "0").strip() or 0)
            exact_count = int((row.get("evidence_exact_count") or "0").strip() or 0)
        except ValueError:
            continue
        total += count
        exact += exact_count
        rows_without_citation += int(count == 0)
        rows_all_verbatim += int(count > 0 and exact_count == count)
        rows_any_verbatim += int(exact_count > 0)
    return {
        "available": True,
        "rows": len(rows),
        "evidence_items": total,
        "verbatim_items": exact,
        "verbatim_share": round(exact / total, 4) if total else 0.0,
        "rows_without_any_citation": rows_without_citation,
        "rows_fully_verbatim": rows_all_verbatim,
        "rows_with_at_least_one_verbatim": rows_any_verbatim,
    }


def fields(rows: list[dict[str, str]], columns: Iterable[str] | None = None) -> dict[str, Any]:
    """Per-column emptiness, flagging columns empty in every row (#450, #452, #453)."""
    columns = list(columns or (rows[0].keys() if rows else []))
    counts = {}
    for column in columns:
        non_empty = sum(1 for row in rows if (row.get(column) or "").strip())
        counts[column] = {"non_empty": non_empty, "empty": len(rows) - non_empty}
    return {
        "rows": len(rows),
        "columns": counts,
        "empty_in_every_row": [c for c, v in counts.items() if v["non_empty"] == 0],
    }


def render(result: dict[str, Any]) -> str:
    lines: list[str] = []
    if "markup" in result:
        data = result["markup"]
        lines += [
            "== markup in stored source text (#449)",
            f"rows {data['rows']}  with any markup {data['rows_with_any_markup']} "
            f"({data['share_with_any_markup']:.1%})  at the {TRUNCATION_CAP:,}-character cap "
            f"{data['rows_at_truncation_cap']}",
            f"  {'platform':10s} {'rows':>6s} {'html':>6s} {'css':>6s} {'js':>6s} {'at cap':>7s} {'tag chars':>10s}",
        ]
        for platform, item in data["per_platform"].items():
            lines.append(f"  {platform:10s} {item['rows']:6d} {item['with_markup']:6d} "
                         f"{item['with_css']:6d} {item['with_script']:6d} {item['at_cap']:7d} "
                         f"{item['markup_share']:10.1%}")
    if "coverage_by_length" in result:
        data = result["coverage_by_length"]
        lines += ["", "== coded-field coverage by source-text length (#451, #460)",
                  f"  {'chars':10s} {'rows':>6s} {'formation':>10s} {'signifiers':>11s} {'antagonisms':>12s}"]
        for name, bucket in data["buckets"].items():
            lines.append(f"  {name:10s} {bucket['rows']:6d} {bucket['shares']['formations']:10.1%} "
                         f"{bucket['shares']['signifiers']:11.1%} {bucket['shares']['antagonisms']:12.1%}")
        zero = data["zero_text"]
        lines.append(f"  zero-text stratum: {zero['rows']} rows coded at {zero['formation_share']:.1%} "
                     f"(formation), {zero['signifier_share']:.1%} (signifiers), "
                     f"{zero['antagonism_share']:.1%} (antagonisms)")
    if "formations" in result:
        data = result["formations"]
        lines += ["", "== formation labels (#454)",
                  f"rows with a label {data['with_label']}  distinct {data['distinct_labels']}  "
                  f"machine-token {data['machine_token_labels']}  prose {data['prose_labels']}",
                  f"top label share {data['top_label_share']:.1%}  singleton labels {data['singleton_labels']}"]
    if "evidence" in result:
        data = result["evidence"]
        lines.append("")
        if not data.get("available"):
            lines.append(f"== citations: not measurable — {data['reason']}")
        else:
            lines += ["== citations (#458)",
                      f"evidence items {data['evidence_items']}  verbatim {data['verbatim_items']} "
                      f"({data['verbatim_share']:.1%})",
                      f"rows without any citation {data['rows_without_any_citation']}  "
                      f"fully verbatim {data['rows_fully_verbatim']}  "
                      f"at least one verbatim {data['rows_with_at_least_one_verbatim']}"]
    if "fields" in result:
        data = result["fields"]
        lines += ["", "== column emptiness (#450, #452, #453)",
                  f"columns {len(data['columns'])}"]
        if data["empty_in_every_row"]:
            lines.append("  EMPTY IN EVERY ROW: " + ", ".join(data["empty_in_every_row"]))
        else:
            lines.append("  no column is empty in every row")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--markup", action="store_true")
    parser.add_argument("--coverage-by-length", action="store_true")
    parser.add_argument("--formations", action="store_true")
    parser.add_argument("--evidence", action="store_true")
    parser.add_argument("--fields", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    try:
        columns, rows = read_export(args.input)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    wanted = {
        "markup": args.markup or args.all,
        "coverage_by_length": args.coverage_by_length or args.all,
        "formations": args.formations or args.all,
        "evidence": args.evidence or args.all,
        "fields": args.fields or args.all,
    }
    if not any(wanted.values()):
        parser.error("choose at least one measurement, or --all")

    result: dict[str, Any] = {"input": str(args.input)}
    if wanted["markup"]:
        result["markup"] = markup(rows)
    if wanted["coverage_by_length"]:
        result["coverage_by_length"] = coverage_by_length(rows)
    if wanted["formations"]:
        result["formations"] = formations(rows)
    if wanted["evidence"]:
        result["evidence"] = evidence([{**row} for row in rows])
    if wanted["fields"]:
        result["fields"] = fields(rows, columns)

    if args.json:
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
