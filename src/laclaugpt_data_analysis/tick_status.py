"""Per-tick outcome for the AI26 analysis wrapper, so a monitor can tell four cases apart (#506).

Before this, a tick that ran well, a tick rejected by the preflight, and a tick that found the
lock held were all just log lines. Cron only saw the exit code, and two of those three exit
non-zero for reasons that are not failures — so "the pipeline is starved" and "the pipeline is
broken" looked the same from outside, which is how three hours of no analysis went unnoticed.

The record is written per tick and is deliberately boring: sanitized scalars only, no record
text, no credentials, no source content. It answers four questions:

* did this tick analyse anything (``outcome``: ok / preflight_rejected / lock_held / failed)
* with what exit code, on which deployed commit
* how many consecutive non-ok ticks preceded it (``consecutive_non_ok``)
* should that raise an alarm (``escalation``, from a threshold the operator sets)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

OUTCOMES = ("ok", "preflight_rejected", "lock_held", "failed")
TICKS_FILE = "ticks.jsonl"
LAST_TICK_FILE = "last-tick.json"
DEFAULT_ESCALATION_THRESHOLD = 3


def build_tick(
    *,
    outcome: str,
    exit_code: int,
    deployed_sha: str = "",
    detail: str = "",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> dict[str, Any]:
    """One tick's outcome as a flat, sanitized record."""
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}; expected one of {OUTCOMES}")
    started = started_at or datetime.now(UTC)
    return {
        "schema_version": 1,
        "outcome": outcome,
        "exit_code": int(exit_code),
        "deployed_sha": str(deployed_sha or "")[:40],
        "detail": str(detail or "")[:400],
        "started_at": started.astimezone(UTC).isoformat(),
        "finished_at": (finished_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
    }


def consecutive_non_ok(records: Iterable[Mapping[str, Any]]) -> int:
    """How many ticks at the end of the sequence did not succeed."""
    count = 0
    for record in records:
        count = 0 if record.get("outcome") == "ok" else count + 1
    return count


def escalation(consecutive: int, threshold: int = DEFAULT_ESCALATION_THRESHOLD) -> str:
    """The alarm text, or an empty string while within tolerance.

    A lock-held tick is not a failure — but N of them in a row means the scheduler is running
    into its own previous tick, and N rejections mean the checkout or the config is wrong.
    Either way the operator wants to know before a day has passed.
    """
    if threshold <= 0 or consecutive < threshold:
        return ""
    return (
        f"AI26 analysis has not completed for {consecutive} consecutive ticks "
        f"(threshold {threshold}); see last-tick.json"
    )


def _read_ticks(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def record_tick(
    directory: str | Path,
    *,
    outcome: str,
    exit_code: int,
    deployed_sha: str = "",
    detail: str = "",
    threshold: int = DEFAULT_ESCALATION_THRESHOLD,
) -> dict[str, Any]:
    """Append the tick, refresh ``last-tick.json``, and return the record with its verdict."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    record = build_tick(outcome=outcome, exit_code=exit_code, deployed_sha=deployed_sha, detail=detail)
    ticks = target / TICKS_FILE
    with ticks.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    history = _read_ticks(ticks)
    record["consecutive_non_ok"] = consecutive_non_ok(history)
    record["escalation"] = escalation(record["consecutive_non_ok"], threshold)
    (target / LAST_TICK_FILE).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record one AI26 analysis tick outcome.")
    parser.add_argument("--directory", required=True, help="tick directory (private runtime state)")
    parser.add_argument("--outcome", required=True, choices=OUTCOMES)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--deployed-sha", default=os.environ.get("LACLAUGPT_DEPLOYED_SHA", ""))
    parser.add_argument("--detail", default="")
    parser.add_argument("--threshold", type=int, default=DEFAULT_ESCALATION_THRESHOLD)
    args = parser.parse_args(argv)
    try:
        record = record_tick(
            args.directory, outcome=args.outcome, exit_code=args.exit_code,
            deployed_sha=args.deployed_sha, detail=args.detail, threshold=args.threshold,
        )
    except OSError as exc:  # a telemetry write must never decide the cycle's fate
        print(json.dumps({"telemetry_error": type(exc).__name__, "outcome": args.outcome}), file=sys.stderr)
        return 0
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
