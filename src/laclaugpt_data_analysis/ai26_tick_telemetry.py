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
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


def append_tick(path: Path, *, stage: str, exit_code: int, check_only: bool,
                worker_status: str = "", report_status: str = "", git_sha: str = "",
                skip_threshold: int = 0, reject_threshold: int = 0,
                progress_path: Path | None = None) -> dict:
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
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
        "stage": stage,
        "exit_code": exit_code,
        "check_only": check_only,
        "worker_status": worker_status or None,
        "report_status": report_status or None,
        "git_sha": git_sha or None,
    }
    if progress_path is not None and stage == "lock":
        # A checkpoint is only evidence of the last completed boundary, not proof
        # that the current model call is hung or healthy.
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            observed = datetime.fromisoformat(progress["timestamp_utc"])
            if observed.tzinfo is None:
                raise ValueError("progress timestamp missing timezone")
            event["progress_age_seconds"] = max(0, int(
                (datetime.now(timezone.utc) - observed).total_seconds()
            ))
            event["progress_phase"] = str(progress.get("phase", ""))[:32]
            event["progress_claims"] = int(progress.get("claims", 0))
            event["progress_completed"] = int(progress.get("completed", 0))
            event["progress_retry"] = int(progress.get("retry", 0))
        except (OSError, ValueError, TypeError, KeyError):
            event["progress_phase"] = "unavailable"
    if skip_threshold < 0 or reject_threshold < 0:
        raise ValueError("thresholds must be >= 0 (zero disables escalation)")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # A single O_APPEND write under flock; do not replace a shared inode.
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_RDWR, 0o600)
    try:
        with os.fdopen(fd, "a+", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            previous = deque(stream, maxlen=100)
            # Count sustained no-progress ticks even when the cause alternates
            # between deployment rejection and an inherited worker lock (#554).
            stalled_streak = 0
            skip_streak = reject_streak = 0
            for raw in reversed(previous):
                try:
                    prior = json.loads(raw)
                except ValueError:
                    continue
                state = prior.get("outcome")
                if state == "check_ok":
                    continue
                if state not in {"already_running", "preflight_rejected"}:
                    break
                stalled_streak += 1
                if state == "already_running":
                    skip_streak += 1
                else:
                    reject_streak += 1
            is_stalled = outcome in {"already_running", "preflight_rejected"}
            event["skip_streak"] = skip_streak + (outcome == "already_running") if is_stalled else 0
            event["reject_streak"] = reject_streak + (outcome == "preflight_rejected") if is_stalled else 0
            event["stalled_streak"] = stalled_streak + 1 if is_stalled else 0
            event["escalation"] = (
                "rejected" if reject_threshold and event["reject_streak"] >= reject_threshold
                else "skipped" if skip_threshold and event["skip_streak"] >= skip_threshold
                else "stalled" if (skip_threshold or reject_threshold)
                and event["stalled_streak"] >= min(
                    threshold for threshold in (skip_threshold, reject_threshold) if threshold
                )
                else None
            )
            if event["escalation"]:
                # #514: the status file is for a watcher; this line is for the operator reading
                # cron's log. Three hours of silence was possible because only one of them existed.
                print(
                    f"ALERT: AI26 analysis is not completing ({event['escalation']}): "
                    f"skip_streak={event['skip_streak']} reject_streak={event['reject_streak']}",
                    file=sys.stderr,
                )
            stream.seek(0, os.SEEK_END)
            stream.write(json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n")
            stream.flush()
            # A stable, private status file can be polled by a host-side watcher.
            # Alarm delivery itself remains an operator choice, not an invented route.
            status_path = path.with_name("ai26-analysis-alert.json")
            temporary = status_path.with_name(status_path.name + "." + str(os.getpid()) + ".tmp")
            try:
                with temporary.open("w", encoding="utf-8") as status:
                    os.chmod(temporary, 0o600)
                    json.dump({k: event[k] for k in ("timestamp_utc", "outcome",
                              "skip_streak", "reject_streak", "stalled_streak", "escalation")}, status)
                    status.write("\n")
                os.replace(temporary, status_path)
            finally:
                if temporary.exists():
                    temporary.unlink()
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
    parser.add_argument("--progress-path", type=Path, default=None)
    parser.add_argument("--skip-threshold", type=int, default=0)
    parser.add_argument("--reject-threshold", type=int, default=0)
    args = parser.parse_args()
    append_tick(args.path, stage=args.stage, exit_code=args.exit_code,
                check_only=args.check_only, worker_status=args.worker_status,
                report_status=args.report_status, git_sha=args.git_sha,
                skip_threshold=args.skip_threshold, reject_threshold=args.reject_threshold,
                progress_path=args.progress_path)


if __name__ == "__main__":
    main()
