"""Per-tick outcome record for the AI26 Laskin analysis wrapper (#506).

The wrapper's history shows three ways a tick can end without doing work, and the log line for each was the
only evidence:

- a **preflight rejection** (exit 2) — configuration or checkout state refused the run;
- a **lock-held skip** (exit 3) — a previous cycle was still holding the fence;
- a **cycle or report failure** (non-zero worker/report status).

Only one of those is a successful tick, yet a monitor reading cron's exit status had no persistent,
structured way to tell them apart over time. This module appends one JSON object per tick and summarises the
tail, so "N consecutive ticks did not analyse anything" is a query rather than an archaeology exercise.

Records carry no private text: outcome, exit code, timestamp, deployed commit and, when known, the counts.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SUCCESS = "success"
OUTCOMES = (SUCCESS, "preflight_rejected", "already_running", "cycle_failed", "report_failed")


def default_path() -> Path:
    """Where the wrapper writes unless told otherwise; beside the other private logs."""
    override = os.environ.get("LACLAUGPT_AI26_TICK_STATUS")
    if override:
        return Path(override)
    private = os.environ.get("LACLAUGPT_PRIVATE_CONFIG_DIR") or os.environ.get("LACLAUGPT_PRIVATE_ROOT", "")
    base = Path(private) / "logs" if private else Path("logs")
    return base / "ai26-analysis-ticks.jsonl"


def append(
    path: Path | str,
    outcome: str,
    exit_code: int,
    *,
    detail: str = "",
    head: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one tick record. Never raises on a full disk — telemetry must not fail a cycle."""
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}; expected one of {OUTCOMES}")
    record: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(),
        "outcome": outcome,
        "exit_code": int(exit_code),
        "host": socket.gethostname(),
        "head": head,
    }
    if detail:
        record["detail"] = detail[:300]
    if extra:
        record.update({k: v for k, v in extra.items() if k not in record})
    try:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        pass
    return record


def tail(path: Path | str, limit: int = 50) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def consecutive_non_success(rows: list[dict[str, Any]]) -> int:
    """How many trailing ticks did not analyse anything."""
    streak = 0
    for row in reversed(rows):
        if row.get("outcome") == SUCCESS:
            break
        streak += 1
    return streak


def summarize(path: Path | str, *, threshold: int = 3, limit: int = 50) -> dict[str, Any]:
    rows = tail(path, limit)
    streak = consecutive_non_success(rows)
    counts: dict[str, int] = {}
    for row in rows:
        outcome = str(row.get("outcome") or "unknown")
        counts[outcome] = counts.get(outcome, 0) + 1
    return {
        "path": str(path),
        "ticks": len(rows),
        "counts": dict(sorted(counts.items())),
        "consecutive_non_success": streak,
        "threshold": threshold,
        "exceeded": streak >= threshold,
        "last": rows[-1] if rows else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="laclaugpt-tick-status", description=__doc__)
    parser.add_argument("action", choices=("record", "summary"))
    parser.add_argument("--path", type=Path, default=None)
    parser.add_argument("--outcome", choices=OUTCOMES)
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--detail", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--threshold", type=int, default=3)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)

    path = args.path or default_path()
    if args.action == "record":
        if not args.outcome:
            parser.error("--outcome is required for record")
        record = append(path, args.outcome, args.exit_code, detail=args.detail, head=args.head)
        print(json.dumps(record, sort_keys=True))
        return 0

    report = summarize(path, threshold=args.threshold, limit=args.limit)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 3 if report["exceeded"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
