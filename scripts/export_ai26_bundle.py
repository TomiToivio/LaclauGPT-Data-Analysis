#!/usr/bin/env python
"""Export a real AI26 Phase 1 researcher bundle (#437).

Read-only with respect to the research record: it loads **already-persisted, completed**
Phase 1 records for one run from the canonical store and writes the canonical bundle
(JSONL + researcher CSV + Markdown + manifest) with :func:`write_research_bundle`.

It never runs analysis, never claims queue work, never rewrites corpus rows, and never
invents records -- the operator decision on #437 is explicit that a bundle must be
actual research output, not synthetic fixtures passed off as a first export.

Privacy: the summary printed here carries counts, a run id, the deployed commit and
paths. It deliberately prints no source text, no author names and no URLs, because the
output goes into a public issue comment.

Usage
-----
    python scripts/export_ai26_bundle.py --list-runs
    python scripts/export_ai26_bundle.py --run-id <id> --output-root <dir> [--limit N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from laclaugpt_data_analysis.config import load_settings
from laclaugpt_data_analysis.exporters import write_research_bundle
from laclaugpt_data_analysis.phase1_laskin_report import load_analysis_records

COMPLETED = "analyzed"


def _collection(settings):
    """The canonical analysis-results collection, mirroring the periodic report."""
    if not settings.mongo_url:
        raise SystemExit("MongoDB is required: no mongo_url in the runtime settings")
    from pymongo import MongoClient

    return MongoClient(settings.mongo_url)[settings.mongo_database][
        settings.distributed_namespace.mongo_collection("analysis_results")
    ]


def list_runs(settings) -> list[dict[str, object]]:
    """Run ids with completed-record counts, newest first. Counts only, no content."""
    pipeline = [
        {"$match": {"project_id": settings.project_id}},
        {"$group": {"_id": "$run_id", "records": {"$sum": 1}}},
        {"$sort": {"records": -1}},
    ]
    return [
        {"run_id": row["_id"], "records": row["records"]}
        for row in _collection(settings).aggregate(pipeline)
        if row.get("_id")
    ]


def _deployed_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list-runs", action="store_true", help="print run ids and record counts, then exit")
    parser.add_argument("--run-id", help="the run to export")
    parser.add_argument("--output-root", type=Path, help="bundle directory to write")
    parser.add_argument("--stem", default="analysis", help="bundle stem (bundle_audit --stem)")
    parser.add_argument("--limit", type=int, default=0, help="cap the number of records (0 = all)")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.list_runs:
        print(json.dumps(list_runs(settings), indent=2, default=str))
        return 0
    if not args.run_id or not args.output_root:
        parser.error("--run-id and --output-root are required unless --list-runs is given")

    records = load_analysis_records(settings, run_id=args.run_id)
    completed = [r for r in records if getattr(r.analysis, "status", "") == COMPLETED]
    if not completed:
        print(json.dumps({"run_id": args.run_id, "status": "no_completed_records",
                          "records_seen": len(records)}, indent=2))
        return 2
    if args.limit:
        completed = completed[: args.limit]

    args.output_root.mkdir(parents=True, exist_ok=True)
    paths = write_research_bundle(completed, args.output_root, stem=args.stem)
    artifacts = {
        Path(p).name: {"sha256": _sha256(Path(p)), "bytes": Path(p).stat().st_size}
        for p in paths.values()
        if isinstance(p, Path) and p.is_file()
    }
    print(json.dumps({
        "run_id": args.run_id,
        "exported_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "deployed_sha": _deployed_sha(),
        "records_exported": len(completed),
        "records_seen_in_run": len(records),
        "output_root": str(args.output_root),
        "artifacts": artifacts,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
