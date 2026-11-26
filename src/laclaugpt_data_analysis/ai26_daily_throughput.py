"""Count completed tasks (not successful cron cycles) from private worker logs."""

from __future__ import annotations

import argparse
import ast
import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_CYCLE = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2})?).*?AI26 worker cycle: (\{[^{}]*\})"
)


def daily_throughput(lines, day: date, *, timezone: str) -> dict:
    """Aggregate only terminal worker summaries, in an explicit local timezone.

    Unknown/malformed summaries are disclosed, and no samples is not a measured zero.
    Counts are attributed to the cycle's finishing day, not individual task timestamps.
    """
    zone = ZoneInfo(timezone)
    completed = duplicates = summaries = malformed = 0
    for line in lines:
        if "AI26 worker cycle:" not in line:
            continue
        match = _CYCLE.search(line)
        if not match:
            malformed += 1
            continue
        try:
            stamp = datetime.fromisoformat(match[1].replace(",", "."))
            stamp = stamp.replace(tzinfo=zone) if stamp.tzinfo is None else stamp.astimezone(zone)
            if stamp.date() != day:
                continue
            counts = ast.literal_eval(match[2])
            new, duplicate = counts["completed"], counts.get("duplicate", 0)
            if any(type(value) is not int or value < 0 for value in (new, duplicate)):
                raise ValueError("Invalid count")
        except (ValueError, SyntaxError, KeyError, TypeError):
            malformed += 1
            continue
        completed += new
        duplicates += duplicate
        summaries += 1
    return {
        "day": day.isoformat(),
        "timezone": timezone,
        "completed_tasks": completed if summaries else None,
        "duplicate_tasks": duplicates if summaries else None,
        "worker_summaries": summaries,
        "malformed_summaries": malformed,
        "coverage": "observed summaries only; missing or malformed cycles may undercount",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--timezone", required=True, help="IANA timezone of naive worker log timestamps"
    )
    args = parser.parse_args()
    with args.log.open(encoding="utf-8", errors="replace") as stream:
        print(json.dumps(daily_throughput(stream, args.day, timezone=args.timezone)))


if __name__ == "__main__":
    main()
