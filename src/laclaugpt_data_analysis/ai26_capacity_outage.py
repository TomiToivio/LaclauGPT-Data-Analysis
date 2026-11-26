"""Name a provider-capacity outage, and say how long it has lasted (#577).

`ai26_daily_throughput` answers "how many tasks completed today". It cannot answer the question an operator
actually asks when that number is zero: *is the worker broken, is the provider out of capacity, or has
nothing been scheduled?* Those three look identical from a throughput count and completely different on the
GPU.

The journal already records the fact per cycle (`outcome=provider_unavailable`, exit 75, and the failure
store's scheduler text). This module turns that stream into the statement the issue asks for: the outage's
start, how many cycles and how many hours it has run, which reasons interleaved, and when work last
completed. Everything is derived from evidence already written; nothing here contacts a host or a provider.

Three semantics are deliberate:

* **Nothing sampled is not zero.** With no events, counts are ``None``, not ``0`` -- an empty journal says
  nothing about the provider, and reporting it as an outage would be an invented incident.
* **A lock is not the outage.** ``already_running`` cycles are reported as reasons inside an interval but do
  not themselves extend the capacity claim: the flock can be held while the endpoint is perfectly healthy.
* **A success ends an interval.** Intervals are segmented by completed cycles, so a park that ends in one
  completed task is not reported as ongoing.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

__all__ = ["Interval", "OutageReport", "summarise"]

#: Outcomes that mean "a cycle ran and did not complete work".
NON_SUCCESS = ("provider_unavailable", "already_running", "preflight_rejected", "cycle_failed")
CAPACITY = "provider_unavailable"


@dataclass
class Interval:
    """A stretch between two completed cycles."""

    started_utc: str
    ended_utc: str
    cycles: int
    reasons: dict[str, int] = field(default_factory=dict)

    @property
    def capacity_parks(self) -> int:
        return self.reasons.get(CAPACITY, 0)

    @property
    def duration_hours(self) -> float:
        start = datetime.fromisoformat(self.started_utc)
        end = datetime.fromisoformat(self.ended_utc)
        return round((end - start).total_seconds() / 3600, 2)

    @property
    def is_capacity(self) -> bool:
        """Whether this interval is evidence of a capacity outage rather than some other stall."""
        return self.capacity_parks > 0


@dataclass
class OutageReport:
    cycles: dict[str, int]
    intervals: list[Interval]
    last_success_utc: str | None
    events: int
    malformed: int
    ongoing: bool

    @property
    def capacity_cycles(self) -> int:
        return self.cycles.get(CAPACITY, 0)

    @property
    def completed_cycles(self) -> int:
        return self.cycles.get("cycle_completed", 0)

    def as_dict(self) -> dict[str, object]:
        current = self.intervals[-1] if self.intervals else None
        return {
            "events": self.events,
            "malformed_events": self.malformed,
            "cycles": dict(sorted(self.cycles.items())),
            "last_success_utc": self.last_success_utc,
            "outage_ongoing": self.ongoing,
            "current_interval_hours": current.duration_hours if current and self.ongoing else 0.0,
            "intervals": [
                {
                    "started_utc": interval.started_utc,
                    "ended_utc": interval.ended_utc,
                    "hours": interval.duration_hours,
                    "cycles": interval.cycles,
                    "reasons": dict(sorted(interval.reasons.items())),
                    "capacity_outage": interval.is_capacity,
                }
                for interval in self.intervals
            ],
            "coverage": (
                "derived from journal events only; a zero event count means nothing was sampled, not an outage"
                if self.events
                else "no journal events: nothing can be concluded about the provider"
            ),
        }

    def sentence(self) -> str:
        """One line an operator or a paper footnote can quote."""
        if not self.events:
            return "no journal events sampled: the provider's state is unknown, not zero"
        if self.ongoing and self.intervals:
            interval = self.intervals[-1]
            last = self.last_success_utc or "never in this journal"
            return (
                f"provider capacity outage ongoing: {interval.capacity_parks} parked cycle(s) over "
                f"{interval.duration_hours} h, last completed cycle {last}, "
                f"{self.completed_cycles} completed of {self.events} cycle event(s)"
            )
        if self.capacity_cycles:
            return (
                f"capacity outage ended: {self.capacity_cycles} parked cycle(s) across "
                f"{sum(1 for i in self.intervals if i.is_capacity)} interval(s); "
                f"last completed cycle {self.last_success_utc or 'never in this journal'}"
            )
        return f"no capacity outage in {self.events} cycle event(s)"


def summarise(lines: Iterable[str]) -> OutageReport:
    events = malformed = 0
    cycles: dict[str, int] = {}
    intervals: list[Interval] = []
    pending: Interval | None = None
    last_success: str | None = None
    last_timestamp: str | None = None

    for raw in lines:
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
            if not isinstance(event, dict):
                raise ValueError("not an object")
            outcome = str(event.get("outcome") or "")
            stamp = str(event.get("timestamp_utc") or "")
            datetime.fromisoformat(stamp)  # a timestamp we cannot read cannot order an outage
        except (ValueError, TypeError):
            malformed += 1
            continue
        if not outcome or not stamp:
            malformed += 1
            continue
        if outcome == "check_ok":
            # A manual preflight is not a cycle; it neither extends nor ends an outage.
            continue
        events += 1
        cycles[outcome] = cycles.get(outcome, 0) + 1
        last_timestamp = stamp
        if outcome == "cycle_completed":
            last_success = stamp
            if pending is not None:
                pending.ended_utc = stamp
                intervals.append(pending)
                pending = None
            continue
        if outcome not in NON_SUCCESS:
            # An unknown outcome is not evidence for either side; it is not counted as a reason.
            continue
        if pending is None:
            pending = Interval(started_utc=stamp, ended_utc=stamp, cycles=0)
        pending.ended_utc = stamp
        pending.cycles += 1
        pending.reasons[outcome] = pending.reasons.get(outcome, 0) + 1

    if pending is not None and last_timestamp is not None:
        pending.ended_utc = last_timestamp
        intervals.append(pending)

    ongoing = bool(pending is not None and pending.is_capacity)
    return OutageReport(
        cycles=cycles,
        intervals=intervals,
        last_success_utc=last_success,
        events=events,
        malformed=malformed,
        ongoing=ongoing,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True, help="AI26 tick journal (JSONL)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    try:
        with args.journal.open(encoding="utf-8", errors="replace") as stream:
            report = summarise(stream)
    except OSError as exc:
        print(f"cannot read journal: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(report.sentence())
        for interval in report.intervals:
            if interval.is_capacity:
                print(
                    f"  {interval.started_utc} -> {interval.ended_utc} "
                    f"({interval.duration_hours} h, {interval.cycles} cycles, "
                    f"{interval.reasons})"
                )
    # Distinct exit status so a cron wrapper can surface an ongoing outage without parsing text.
    return 3 if report.ongoing else 0


if __name__ == "__main__":
    raise SystemExit(main())
