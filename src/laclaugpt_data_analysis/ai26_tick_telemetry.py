"""Append sanitized AI26 cron-tick outcomes to a private, queryable JSONL journal.

No credentials, source text, prompts, host paths or environment values are recorded.
An advisory lock prevents concurrent cron ticks from interleaving JSON writes.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from datetime import UTC, datetime
from pathlib import Path


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
    args = parser.parse_args()
    append_tick(args.path, stage=args.stage, exit_code=args.exit_code,
                check_only=args.check_only, worker_status=args.worker_status,
                report_status=args.report_status, git_sha=args.git_sha)


if __name__ == "__main__":
    main()
