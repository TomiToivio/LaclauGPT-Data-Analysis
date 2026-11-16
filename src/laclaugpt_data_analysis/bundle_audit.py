"""Offline, privacy-safe integrity audit for AI26 researcher bundles (#437).

Adapted from the failure classes in upstream EP24 export-bundle QA (#407),
not from EP24's scientific pipeline or data schema. No source text or IDs
are included in the returned diagnostics.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def audit_research_bundle(root: str | Path, *, stem: str = "analysis") -> dict[str, Any]:
    """Check export identities, parseability and representation counts without a database.

    Raises no exception for malformed research artifacts; returns a failed audit.
    Only counts, paths, and hashes are emitted, never source text or source IDs.
    """
    directory = Path(root)
    jsonl = directory / f"{stem}.jsonl"
    csv_path = directory / f"{stem}_researchers.csv"
    reports_dir = directory / f"{stem}_reports"
    problems: list[str] = []
    result: dict[str, Any] = {"ok": False, "counts": {}, "sha256": {}, "problems": problems}
    ids: dict[str, list[str]] = {}

    for label, path in (("jsonl", jsonl), ("csv", csv_path)):
        if not path.is_file():
            problems.append(f"{label}_missing")
            continue
        result["sha256"][label] = hashlib.sha256(path.read_bytes()).hexdigest()
        records: list[str] = []
        try:
            if label == "jsonl":
                with path.open(encoding="utf-8") as handle:
                    for line in handle:
                        if not line.strip():
                            continue
                        obj = json.loads(line)
                        if not isinstance(obj, dict):
                            raise ValueError("JSONL entry is not an object")
                        records.append(str(obj.get("source_url") or "").strip())
            else:
                with path.open(encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    if not reader.fieldnames or "source_url" not in reader.fieldnames:
                        problems.append("csv_source_url_header_missing")
                    else:
                        for row in reader:
                            if None in row:
                                problems.append("csv_row_width_mismatch")
                            records.append(str(row.get("source_url") or "").strip())
        except (OSError, UnicodeError, ValueError, csv.Error):
            # No exception messages: they may contain private data.
            problems.append(f"{label}_unreadable_or_invalid")
            result["counts"][label] = len(records)
            continue
        ids[label] = records
        result["counts"][label] = len(records)
        if any(not key for key in records):
            problems.append(f"{label}_missing_identity")
        if len(set(records)) != len(records):
            problems.append(f"{label}_duplicate_identity")

    if "jsonl" in ids and "csv" in ids:
        if Counter(ids["jsonl"]) != Counter(ids["csv"]):
            problems.append("jsonl_csv_identity_mismatch")

    if not reports_dir.is_dir():
        problems.append("reports_directory_missing")
    else:
        reports = list(reports_dir.glob("*.md"))
        result["counts"]["reports"] = len(reports)
        if "jsonl" in ids and len(reports) != len(ids["jsonl"]):
            problems.append("report_count_mismatch")

    result["ok"] = not problems
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Directory containing a researcher bundle")
    parser.add_argument("--stem", default="analysis")
    args = parser.parse_args(argv)
    report = audit_research_bundle(args.root, stem=args.stem)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
