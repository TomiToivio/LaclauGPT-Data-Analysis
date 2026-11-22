"""Append sanitized AI26 cron-tick outcomes to a private, queryable JSONL journal.

No credentials, source text, prompts, host paths or environment values are recorded.
An advisory lock prevents concurrent cron ticks from interleaving JSON writes.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

#: Outcomes that mean a tick did something. Everything else is a tick that did not.
PRODUCTIVE_OUTCOMES = ("cycle_completed", "check_ok")


def consecutive_non_productive(rows: list[dict]) -> int:
    """How many trailing ticks neither completed a cycle nor ran a verification."""
    streak = 0
    for row in reversed(rows):
        if row.get("outcome") in PRODUCTIVE_OUTCOMES:
            break
        streak += 1
    return streak


def recent_ticks(path: Path, limit: int = 50) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_tick(path: Path, *, stage: str, exit_code: int, check_only: bool,
                worker_status: str = "", report_status: str = "", git_sha: str = "") -> dict:
    """Write exactly one atomic JSONL event per invocation, including skipped ticks."""
    if exit_code == 3:
        outcome = "already_running"
    elif exit_code != 0 and stage == "preflight":
        outcome = "preflight_rejected"
    elif check_only and exit_code == 0:
        outcome = "check_ok"
    elif exit_code == 0:
        outcome = "cycle_completed"
    else:
        outcome = "cycle_failed"
    event = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "outcome": outcome,
        "stage": stage,
        "exit_code": exit_code,
        "check_only": check_only,
        "worker_status": worker_status or None,
        "report_status": report_status or None,
        "git_sha": git_sha or None,
    }
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # A single O_APPEND write under flock; do not replace a shared inode.
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n")
            stream.flush()
            fcntl.flock(stream, fcntl.LOCK_UN)
    finally:
        # fdopen owns the descriptor after success; do not double-close.
        pass
    return event


def main() -> None:
    parser = argparse.ArgumentParser(description="Record sanitized AI26 cron outcome in private JSONL")
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--stage", required=True, choices=("preflight", "check", "lock", "worker", "complete"))
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--worker-status", default="")
    parser.add_argument("--report-status", default="")
    parser.add_argument("--git-sha", default="")
    parser.add_argument("--escalate-after", type=int, default=3,
                        help="consecutive unproductive ticks before escalation (#514)")
    args = parser.parse_args()
    event = append_tick(args.path, stage=args.stage, exit_code=args.exit_code,
                        check_only=args.check_only, worker_status=args.worker_status,
                        report_status=args.report_status, git_sha=args.git_sha)
    # #514: a journal nobody reads is not monitoring. Escalation is reported on stderr so the
    # wrapper's log carries it, and the threshold is an operator setting rather than a constant
    # baked into the writer.
    streak = consecutive_non_productive(recent_ticks(args.path))
    if args.escalate_after > 0 and streak >= args.escalate_after:
        print(
            f"ESCALATION: {streak} consecutive AI26 ticks did not complete a cycle "
            f"(threshold {args.escalate_after}); last outcome={event['outcome']} "
            f"exit_code={event['exit_code']} stage={event['stage']}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
