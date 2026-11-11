"""Measure the AI26 ready frame against what has actually been analysed (#429).

The seeding order is ``(source_priority, published_at DESC, source_url)`` and a cycle stops after
``LACLAUGPT_MAX_TASKS`` publications. When one priority tier is larger than a cycle's capacity, the
tiers behind it are never reached — the ready frame keeps growing while a fixed pool of documents
is never analysed at all. Nothing in the pipeline reports that, because every individual cycle
looks healthy: it examined a few thousand records and published its ten.

This tool makes the property visible and checkable:

* the ready frame in the seeding order, with the position where each platform's first
  never-analysed document sits — the number that explains why it is never reached;
* per-platform analysed share, so a platform that is falling behind is visible as a trend
  rather than as an anecdote;
* the never-analysed pool by platform and publication month, which is the backlog the
  priority order is starving.

It is read-only: it never writes to the store, and it never publishes a task.

Usage::

    set -a; . ./.env; set +a
    .venv/bin/python tools/ai26_ready_frame_audit.py --json
    .venv/bin/python tools/ai26_ready_frame_audit.py --project-id ai26 --fail-under 0.80

Exit codes: 0 measured and within the given bounds, 1 a platform is below ``--fail-under``,
2 the store could not be read.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

#: The platform whose documents were deliberately closed (#401) and are therefore excluded from
#: the starvation verdict. It is still reported, because a closed stratum that is visible is
#: different from one that has quietly gone missing.
CLOSED_PLATFORMS = frozenset({"x"})

#: A platform whose analysed share falls below this is behind, not merely uneven. The issue states
#: the paper's evaluation sample is drawn from analysed documents, so an under-represented platform
#: is a coverage property of Phase 1 rather than an operational detail.
DEFAULT_FAIL_UNDER = 0.80


def platform_of(record: Mapping[str, Any]) -> str:
    source = record.get("source") or {}
    platform = source.get("platform") if isinstance(source, Mapping) else None
    return str(platform or "unknown")


def month_of(record: Mapping[str, Any]) -> str:
    handoff = record.get("handoff") or {}
    value = handoff.get("published_at") if isinstance(handoff, Mapping) else None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m")
    text = str(value or "")
    return text[:7] if len(text) >= 7 else "unknown"


def seeding_order(records: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Sort the ready frame exactly as ``MongoCollectionHandoff.ready_handoffs`` sorts it.

    Reproducing the order here rather than trusting a caller's query is the point: the audit must
    measure the frame the worker will actually walk, including the ``published_at DESC`` tiebreak
    that pushes October to the back.
    """
    return sorted(
        records,
        key=lambda record: (
            int((record.get("handoff") or {}).get("source_priority") or 0),
            _descending_timestamp((record.get("handoff") or {}).get("published_at")),
            str(record.get("source_url") or ""),
        ),
    )


def _descending_timestamp(value: Any) -> float:
    """A key that sorts newest-first inside an ascending sort."""
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return -moment.timestamp()
    text = str(value or "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return -datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return 0.0


def audit(records: Sequence[Mapping[str, Any]], analysed_urls: Iterable[str]) -> dict[str, Any]:
    """Summarise the frame: per-platform shares, first unreached position, backlog by month."""
    done = set(analysed_urls)
    ordered = seeding_order(records)

    ready: dict[str, int] = defaultdict(int)
    analysed: dict[str, int] = defaultdict(int)
    first_unanalysed: dict[str, int] = {}
    backlog_months: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for position, record in enumerate(ordered, start=1):
        platform = platform_of(record)
        ready[platform] += 1
        url = str(record.get("source_url") or "")
        if url in done:
            analysed[platform] += 1
            continue
        first_unanalysed.setdefault(platform, position)
        backlog_months[platform][month_of(record)] += 1

    platforms = {}
    for platform in sorted(ready):
        share = analysed[platform] / ready[platform] if ready[platform] else 0.0
        platforms[platform] = {
            "ready": ready[platform],
            "analysed": analysed[platform],
            "share": round(share, 4),
            "first_never_analysed_position": first_unanalysed.get(platform),
            "closed_stratum": platform in CLOSED_PLATFORMS,
            "never_analysed": sum(backlog_months[platform].values()),
            "never_analysed_by_month": dict(sorted(backlog_months[platform].items())),
        }

    reachable = {
        name: row["first_never_analysed_position"]
        for name, row in platforms.items()
        if not row["closed_stratum"] and row["first_never_analysed_position"]
    }
    return {
        "ready": len(ordered),
        "analysed": sum(1 for record in ordered if str(record.get("source_url") or "") in done),
        "never_analysed": sum(row["never_analysed"] for row in platforms.values()),
        "platforms": platforms,
        "first_never_analysed": reachable,
        # The reachable tail starts where the cheapest tier ends: a cycle of N publications cannot
        # pass a tier that is larger than the walk it can afford (#429).
        "deepest_tier_boundary": max(
            (row["first_never_analysed_position"] or 0 for row in platforms.values()),
            default=0,
        ),
    }


def verdict(report: Mapping[str, Any], *, fail_under: float = DEFAULT_FAIL_UNDER) -> list[str]:
    """Name the platforms that are behind, ignoring closed strata."""
    problems = []
    for platform, row in report["platforms"].items():
        if row["closed_stratum"] or not row["ready"]:
            continue
        if row["share"] < fail_under:
            problems.append(
                f"{platform}: {row['analysed']}/{row['ready']} analysed "
                f"({row['share']:.1%}), first unanalysed at position "
                f"{row['first_never_analysed_position']}"
            )
    return problems


def render(report: Mapping[str, Any]) -> str:
    lines = [
        f"ready {report['ready']}  analysed {report['analysed']}  "
        f"never analysed {report['never_analysed']}",
        "",
        "| platform | ready | analysed | share | first never-analysed |",
        "|---|---|---|---|---|",
    ]
    for platform, row in report["platforms"].items():
        position = row["first_never_analysed_position"] or "-"
        flag = " (closed stratum)" if row["closed_stratum"] else ""
        lines.append(
            f"| {platform}{flag} | {row['ready']} | {row['analysed']} | "
            f"{row['share']:.1%} | {position} |"
        )
    months = {
        (platform, month): count
        for platform, row in report["platforms"].items()
        for month, count in row["never_analysed_by_month"].items()
    }
    if months:
        lines += ["", "never analysed, by platform and publication month:"]
        for (platform, month), count in sorted(months.items()):
            lines.append(f"  {platform} {month}: {count}")
    return "\n".join(lines)


def read_frame(uri: str, database: str, project_id: str) -> tuple[list[dict], set[str]]:
    """Read the ready frame and the analysed URLs. Read-only by construction."""
    from pymongo import MongoClient

    with MongoClient(uri) as client:
        db = client[database]
        records = list(
            db[f"{project_id}__records"].find(
                {"project_id": project_id, "handoff.status": "ready"},
                {
                    "source_url": 1,
                    "source.platform": 1,
                    "handoff.source_priority": 1,
                    "handoff.published_at": 1,
                    "_id": 0,
                },
            )
        )
        analysed = {
            row["source_url"]
            for row in db[f"{project_id}__analysis_results"].find(
                {"project_id": project_id}, {"source_url": 1, "_id": 0}
            )
            if row.get("source_url")
        }
    return records, analysed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the AI26 ready frame against results (#429).")
    parser.add_argument("--project-id", default=os.getenv("LACLAUGPT_PROJECT_ID", "ai26"))
    parser.add_argument("--database", default=os.getenv("LACLAUGPT_MONGODB_DATABASE", ""))
    parser.add_argument("--uri-env", default="LACLAUGPT_MONGODB_URI")
    parser.add_argument("--fail-under", type=float, default=DEFAULT_FAIL_UNDER,
                        help="exit 1 when a non-closed platform's analysed share is below this")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    uri = (os.getenv(args.uri_env) or "").strip()
    database = (args.database or "").strip()
    if not uri or not database:
        print(
            f"missing store configuration: set {args.uri_env} and LACLAUGPT_MONGODB_DATABASE",
            file=sys.stderr,
        )
        return 2
    try:
        records, analysed = read_frame(uri, database, args.project_id)
    except Exception as exc:  # noqa: BLE001 - the report must say why it could not read the store
        print(f"cannot read the store: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    report = audit(records, analysed)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render(report))
        problems = verdict(report, fail_under=args.fail_under)
        if problems:
            print("\nbehind:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
    return 1 if verdict(report, fail_under=args.fail_under) else 0


if __name__ == "__main__":
    raise SystemExit(main())
