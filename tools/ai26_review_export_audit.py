#!/usr/bin/env python3
"""Audit the private AI26 human-review CSV without exposing source-level content.

Issue #444. Read-only, standard-library-only. The audit is *structural*, not an
accuracy verdict. Do not publish the input, sample identities, or reviewer notes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REQUIRED = (
    "source_url", "platform", "arena", "source_text", "analysis_status",
    "analysis_summary", "review_note",
)
#: A source text can hold a whole transcript, and the csv module refuses any cell over 128 kB by
#: default -- which surfaced as a bare "Error" on the first real export.
MAX_FIELD_BYTES = 64 * 1024 * 1024
csv.field_size_limit(MAX_FIELD_BYTES)

INTERPRETATIONS = (
    "formations", "signifiers", "nodal_points", "floating_signifiers",
    "imaginaries", "discourses", "antagonisms",
)


def _hint(error: Exception) -> str:
    """Safe, actionable diagnosis: never the exception text, which can contain cell content."""
    text = str(error).lower()
    if isinstance(error, csv.Error) and "field larger than field limit" in text:
        return (f"a cell exceeds the CSV field limit ({MAX_FIELD_BYTES} bytes); "
                "the export carries whole source texts")
    if isinstance(error, FileNotFoundError):
        return "a required file is missing"
    if isinstance(error, PermissionError):
        return "a required file is not readable"
    if isinstance(error, json.JSONDecodeError):
        return "the manifest is not valid JSON"
    if isinstance(error, KeyError):
        return "the manifest is missing a required field"
    if isinstance(error, ValueError):
        return "a contract check failed (schema, digest, row count, columns or identifiers)"
    return "I/O failure"


def audit(csv_path: Path, manifest_path: Path, *, seed: int = 444,
          per_stratum: int = 3) -> tuple[dict, list[dict]]:
    """Return safe aggregates and *private* sampled rows."""
    if per_stratum < 1:
        raise ValueError("per_stratum must be positive")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "ai26.human_review/1":
        raise ValueError("Unexpected/missing review-export schema")
    checksum = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if checksum != manifest.get("file_sha256"):
        raise ValueError("CSV SHA256 disagrees with manifest")
    with csv_path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        headers = reader.fieldnames or []
        if any(field not in headers for field in REQUIRED):
            raise ValueError("Required review columns missing")
        if len(set(headers)) != len(headers):
            raise ValueError("Duplicate CSV column names")
        rows = list(reader)
    if not rows:
        raise ValueError("Review export is empty: no accuracy audit can be performed")
    if len(rows) != manifest.get("exported_rows"):
        raise ValueError("CSV row count disagrees with manifest")
    ids = [r["source_url"].strip() for r in rows]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("Missing or duplicated source_url")
    rng = random.Random(seed)
    status_counts = Counter()
    missing = Counter()
    by_arena = Counter()
    by_platform = Counter()
    strata = defaultdict(list)
    for row in rows:
        status = row["analysis_status"].strip() or "(empty)"
        arena = row["arena"].strip() or "(unknown)"
        platform = row["platform"].strip() or "(unknown)"
        by_arena[arena] += 1
        by_platform[platform] += 1
        status_counts[status] += 1
        for field in ("source_text", "analysis_summary", *INTERPRETATIONS):
            if field in row and not row[field].strip():
                missing[field] += 1
        # Stratify on actual metadata; no guessed language/model fields.
        strata[(arena, platform, bool(row["analysis_summary"].strip()))].append(row)
    samples = []
    for key in sorted(strata):
        group = sorted(strata[key], key=lambda r: r["source_url"])
        samples.extend(rng.sample(group, min(per_stratum, len(group))))
    report = {
        "contract": "ai26-review-audit/1",
        "export_sha256": checksum,
        "generated_at_utc": manifest.get("generated_at_utc"),
        "rows": len(rows),
        "sample_seed": seed,
        "sample_per_stratum": per_stratum,
        "sample_rows": len(samples),
        "sample_strata": len(strata),
        "statuses": dict(sorted(status_counts.items())),
        "arenas": dict(sorted(by_arena.items())),
        "platforms": dict(sorted(by_platform.items())),
        "missing_by_field": dict(sorted(missing.items())),
        # A field missing from every row is not "sparse data": nothing produces it. The difference
        # decides whether a researcher reports a finding or files a pipeline defect.
        "empty_in_every_row": sorted(field for field, count in missing.items() if count == len(rows)),
        "accuracy_assessed": False,
        "interpretation": "Structural profiling only; researcher review of source evidence required",
    }
    return report, samples


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True,
                        help="Aggregated report only, may be shared after disclosure review")
    parser.add_argument("--private-sample", type=Path, required=True,
                        help="Private CSV: full sampled source and analysis content")
    parser.add_argument("--seed", type=int, default=444)
    parser.add_argument("--per-stratum", type=int, default=3)
    args = parser.parse_args(argv)
    if args.report.resolve() == args.private_sample.resolve():
        parser.error("Report and private sample must be different files")
    try:
        report, sample = audit(args.input, args.manifest, seed=args.seed,
                               per_stratum=args.per_stratum)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.private_sample.parent.mkdir(parents=True, exist_ok=True)
        # Do not print or store individual URLs in aggregate JSON.
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
        with args.private_sample.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(sample[0]))
            writer.writeheader()
            writer.writerows(sample)
        print(f"Audited {report['rows']} rows; private review sample {len(sample)} rows")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, csv.Error) as error:
        # The message of a csv/OS error can quote a cell or a path, so print a diagnosis rather than
        # the exception text: a failure that only says "Error" hides a fixable cause.
        print(f"AI26 audit failed: {type(error).__name__}: {_hint(error)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
