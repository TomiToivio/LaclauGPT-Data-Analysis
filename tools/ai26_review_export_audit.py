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

REQUIRED = ("source_url",)
# Two review projections exist: the richer export has source_text/formations,
# while the compact human-review projection uses text_excerpt/formation.
# Missing source evidence and omitted projections must remain distinguishable.
ALIASES = {
    "source_text": ("source_text", "text_excerpt"),
    "analysis_summary": ("analysis_summary", "summary"),
    "formations": ("formations", "formation"),
    "analysis_status": ("analysis_status", "discourse_status", "status"),
}
INTERPRETATIONS = (
    "formations", "signifiers", "nodal_points", "floating_signifiers",
    "imaginaries", "discourses", "antagonisms",
)


def _column(headers: list[str], logical: str) -> str | None:
    candidates = ALIASES.get(logical, (logical,))
    return next((name for name in candidates if name in headers), None)


def _value(row: dict, headers: list[str], logical: str) -> str:
    column = _column(headers, logical)
    return (row.get(column) or "").strip() if column else ""


def audit(csv_path: Path, manifest_path: Path, *, seed: int = 444,
          per_stratum: int = 3) -> tuple[dict, list[dict]]:
    """Return safe aggregates and *private* sampled rows."""
    if per_stratum < 1:
        raise ValueError("per_stratum must be positive")
    manifest_text = manifest_path.read_text(encoding="utf-8")
    if manifest_text.startswith("version https://git-lfs.github.com/spec/v1"):
        raise ValueError("Git LFS manifest pointer; hydrate private data with git lfs pull")
    if csv_path.open("rb").read(80).startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise ValueError("Git LFS CSV pointer; hydrate private data with git lfs pull")
    manifest = json.loads(manifest_text)
    # Require verifiable provenance instead of silently treating an arbitrary CSV
    # as an AI26 export. Variant field names are allowed only when present.
    if manifest.get("schema") not in (None, "ai26.human_review/1", "ai26.review/1"):
        raise ValueError("Unexpected review-export schema")
    checksum = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    expected_digest = manifest.get("file_sha256") or manifest.get("sha256")
    if not expected_digest or checksum != expected_digest:
        raise ValueError("CSV SHA256 missing or disagrees with manifest")
    with csv_path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        headers = reader.fieldnames or []
        if any(field not in headers for field in REQUIRED):
            raise ValueError("Required review columns missing")
        if not _column(headers, "analysis_summary"):
            raise ValueError("No readable AI26 analysis summary column")
        if not _column(headers, "source_text"):
            raise ValueError("No source evidence text/excerpt column")
        if len(set(headers)) != len(headers):
            raise ValueError("Duplicate CSV column names")
        rows = list(reader)
    if not rows:
        raise ValueError("Review export is empty: no accuracy audit can be performed")
    expected_rows = manifest.get("exported_rows", manifest.get("rows"))
    if expected_rows is None or len(rows) != expected_rows:
        raise ValueError("CSV row count missing or disagrees with manifest")
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
        status = _value(row, headers, "analysis_status") or "(unknown)"
        arena = _value(row, headers, "arena") or "(unknown)"
        platform = _value(row, headers, "platform") or "(unknown)"
        by_arena[arena] += 1
        by_platform[platform] += 1
        status_counts[status] += 1
        for field in ("source_text", "analysis_summary", *INTERPRETATIONS):
            if _column(headers, field) and not _value(row, headers, field):
                missing[field] += 1
        # Stratify only on available fields; missing excerpt is not proof that
        # the *full* canonical source record contains no evidence.
        strata[(arena, platform, bool(_value(row, headers, "analysis_summary")),
                bool(_value(row, headers, "source_text")),
                bool(_value(row, headers, "formations")))].append(row)
    samples = []
    for key in sorted(strata):
        group = sorted(strata[key], key=lambda r: r["source_url"])
        samples.extend(rng.sample(group, min(per_stratum, len(group))))
    report = {
        "contract": "ai26-review-audit/1",
        "export_sha256": checksum,
        "generated_at_utc": manifest.get("generated_at_utc") or manifest.get("generated_at"),
        "rows": len(rows),
        "sample_seed": seed,
        "sample_per_stratum": per_stratum,
        "sample_rows": len(samples),
        "sample_strata": len(strata),
        "statuses": dict(sorted(status_counts.items())),
        "arenas": dict(sorted(by_arena.items())),
        "platforms": dict(sorted(by_platform.items())),
        "missing_by_field": dict(sorted(missing.items())),
        "projected_columns": {name: _column(headers, name) for name in
                              ("source_text", "analysis_summary", "formations")},
        "source_text_is_excerpt": _column(headers, "source_text") == "text_excerpt",
        "accuracy_assessed": False,
        "interpretation": "Structural profiling only; a short source excerpt cannot establish quote fidelity or coding accuracy",
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
        # Do not print exception content: it can contain sensitive data/paths.
        print(f"AI26 audit failed: {type(error).__name__}; check input and manifest",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
