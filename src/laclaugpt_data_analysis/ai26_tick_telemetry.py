"""Append sanitized AI26 cron-tick outcomes to a private, queryable JSONL journal.

No credentials, source text, prompts, host paths or environment values are recorded.
An advisory lock prevents concurrent cron ticks from interleaving JSON writes.

Four things this has to get right, each learned from a silent failure on Laskin:

* **Run on the host's interpreter.** This module is invoked by the wrapper, which uses the
  system ``python3`` (3.10 on Ubuntu 22.04). ``datetime.UTC`` is 3.11+, so importing it crashed
  the writer on every tick while reporting only a warning (#516).
* **Record the check path.** A ``--check`` tick is a tick; leaving it out made the journal
  disagree with what the operator had just run (#513).
* **Say how a lock holder is doing.** ``already_running`` alone cannot distinguish a busy
  worker from a hung one, so the caller passes a detail and may override the outcome (#512).
* **Raise its voice when ticks keep failing.** A journal nobody reads is not a monitor (#514).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

#: Outcomes that mean the pipeline did its job. ``check_ok`` is deliberately included: a
#: verification tick proves the configuration, so it resets a streak rather than extending it.
HEALTHY_OUTCOMES = frozenset({"cycle_completed", "check_ok"})

DEFAULT_ESCALATE_AFTER = 3
DEFAULT_REJECT_AFTER = 2


def classify(stage: str, exit_code: int, check_only: bool, outcome_override: str = "") -> str:
    """The outcome name for one tick. An override wins, because the caller knows more.

    The lock path uses it to say ``stale_lock``: exit 3 is correct either way, but a lock held
    by a worker that stopped writing is not the same event as a healthy overlap (#512).
    """
    if outcome_override:
        return outcome_override
    if exit_code == 3:
        return "already_running"
    if exit_code != 0 and stage == "preflight":
        return "preflight_rejected"
    if check_only and exit_code == 0:
        return "check_ok"
    if exit_code == 0:
        return "cycle_completed"
    if exit_code == 4:
        # The worker finished; the periodic report failed. Different remedy from a task failure,
        # so it gets a different name rather than being folded into cycle_failed.
        return "report_failed"
    return "cycle_failed"


def _read_events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    events = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def streak(events: Iterable[dict]) -> tuple[int, int]:
    """(consecutive non-healthy ticks, consecutive preflight rejections) at the tail."""
    unhealthy = rejections = 0
    for event in events:
        outcome = event.get("outcome")
        unhealthy = 0 if outcome in HEALTHY_OUTCOMES else unhealthy + 1
        rejections = rejections + 1 if outcome == "preflight_rejected" else 0
    return unhealthy, rejections


def escalation(unhealthy: int, rejections: int, *, escalate_after: int, reject_after: int) -> str:
    """The alarm text, or "" while within tolerance.

    A rejection escalates sooner than a skip: bad code or bad config does not fix itself,
    while an overlapping cycle usually resolves on the next tick.
    """
    if reject_after > 0 and rejections >= reject_after:
        return (f"AI26 analysis preflight rejected {rejections} consecutive ticks "
                f"(threshold {reject_after}); the checkout or configuration needs a human")
    if escalate_after > 0 and unhealthy >= escalate_after:
        return (f"AI26 analysis has not completed for {unhealthy} consecutive ticks "
                f"(threshold {escalate_after}); see the tick journal")
    return ""


def append_tick(path: Path, *, stage: str, exit_code: int, check_only: bool,
                worker_status: str = "", report_status: str = "", git_sha: str = "",
                detail: str = "", outcome_override: str = "",
                escalate_after: int = DEFAULT_ESCALATE_AFTER,
                reject_after: int = DEFAULT_REJECT_AFTER) -> dict:
    """Write exactly one atomic JSONL event per invocation, including skipped ticks."""
    prior_unhealthy, prior_rejections = streak(_read_events(path))
    outcome = classify(stage, exit_code, check_only, outcome_override)
    unhealthy = 0 if outcome in HEALTHY_OUTCOMES else prior_unhealthy + 1
    rejections = prior_rejections + 1 if outcome == "preflight_rejected" else 0
    alarm = escalation(unhealthy, rejections, escalate_after=escalate_after,
                       reject_after=reject_after)
    event = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
        "stage": stage,
        "exit_code": exit_code,
        "check_only": check_only,
        "worker_status": worker_status or None,
        "report_status": report_status or None,
        "git_sha": git_sha or None,
        "detail": detail[:400] or None,
        "consecutive_unhealthy": unhealthy,
        "escalation": alarm or None,
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
    if alarm:
        # stderr reaches cron's log; the journal reaches whoever looks. Both, always (#514).
        print(f"ALERT: {alarm}", file=sys.stderr)
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
    parser.add_argument("--detail", default="")
    parser.add_argument("--outcome", default="", help="override the derived outcome (e.g. stale_lock)")
    parser.add_argument("--escalate-after", type=int, default=DEFAULT_ESCALATE_AFTER)
    parser.add_argument("--reject-after", type=int, default=DEFAULT_REJECT_AFTER)
    args = parser.parse_args()
    append_tick(args.path, stage=args.stage, exit_code=args.exit_code,
                check_only=args.check_only, worker_status=args.worker_status,
                report_status=args.report_status, git_sha=args.git_sha,
                detail=args.detail, outcome_override=args.outcome,
                escalate_after=args.escalate_after, reject_after=args.reject_after)


if __name__ == "__main__":
    main()
