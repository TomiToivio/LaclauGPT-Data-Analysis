"""AI26 prompt-budget audit (#425).

Turns the worker log into the table the throughput decision actually needs. The issue asked whether to
raise the output ceiling or lower the source cap; the log answers a different question first — how often
the prompt is saturated at all, and which sections pay for it.

Read-only: the log is opened, nothing else is touched.

    python tools/ai26_prompt_budget_audit.py --log <analysis log>
    python tools/ai26_prompt_budget_audit.py --log <analysis log> --json
    python tools/ai26_prompt_budget_audit.py --log <analysis log> --days 7

Why a tool and not a one-off grep: the decision is a ratio, and the ratio changes. A day with 8
truncations and a day with 64 mean different things unless you know how many cycles ran and how much
of the budget was spent on which section.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

CYCLE_MARKER = "AI26 worker cycle: "
TRUNC_RE = re.compile(r"structured generation truncated.*?num_predict=(\d+)")
BUDGET_RE = re.compile(r"prompt budget: (\d+) chars.*?used (\d+)")
SECTION_RE = re.compile(r"([a-z_]+): ([\d,]+) chars,.*?(full|truncated \(exceeds its section cap\)"
                        r"|omitted \(no budget left[^)]*\))")
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


@dataclass
class Day:
    date: str
    cycles: int = 0
    completed: int = 0
    retry: int = 0
    dead: int = 0
    trunc: Counter = field(default_factory=Counter)
    budget_lines: int = 0
    saturated: int = 0
    capped: Counter = field(default_factory=Counter)
    omitted: Counter = field(default_factory=Counter)

    @property
    def truncations(self) -> int:
        return sum(self.trunc.values())

    def as_dict(self) -> dict:
        return {
            "date": self.date, "cycles": self.cycles, "completed": self.completed,
            "retry": self.retry, "dead_letter": self.dead,
            "truncations": self.truncations,
            "truncations_by_rung": dict(sorted(self.trunc.items())),
            "budget_lines": self.budget_lines, "saturated_lines": self.saturated,
            "capped_by_section": dict(sorted(self.capped.items())),
            "omitted_by_section": dict(sorted(self.omitted.items())),
        }


def _first_brace_block(text: str) -> str:
    """The worker line has more dicts after the cycle dict; take only the first balanced block."""
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    for position in range(start, len(text)):
        char = text[position]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:position + 1]
    return ""


def _cycle_counts(payload: str) -> tuple[int, int, int] | None:
    """The worker prints a Python-dict literal; parse it rather than regex the fields."""
    try:
        parsed = ast.literal_eval(payload)
    except (ValueError, SyntaxError):
        return None
    if not isinstance(parsed, dict):
        return None
    def number(key: str) -> int:
        try:
            return int(parsed.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0
    return number("completed"), number("retry"), number("dead-letter")


def audit(lines: Iterable[str]) -> list[Day]:
    days: dict[str, Day] = defaultdict(lambda: Day(date=""))
    for raw in lines:
        line = raw.rstrip("\n")
        match = DATE_RE.match(line)
        if not match:
            continue
        day = days[match.group(1)]
        day.date = match.group(1)

        if CYCLE_MARKER in line:
            payload = _first_brace_block(line.split(CYCLE_MARKER, 1)[1])
            counts = _cycle_counts(payload) if payload else None
            if counts:
                day.cycles += 1
                day.completed += counts[0]
                day.retry += counts[1]
                day.dead += counts[2]
            continue

        if trunc := TRUNC_RE.search(line):
            day.trunc[trunc.group(1)] += 1
            continue

        if BUDGET_RE.search(line):
            day.budget_lines += 1
            dropped = False
            for name, _chars, state in SECTION_RE.findall(line):
                if state.startswith("truncated"):
                    day.capped[name] += 1
                elif state.startswith("omitted"):
                    day.omitted[name] += 1
                    dropped = True
            # A line is starved once, however many sections it lost: the denominator is prompt builds.
            if dropped:
                day.saturated += 1
            continue
    return [days[key] for key in sorted(days)]


def render(days: list[Day]) -> str:
    if not days:
        return "no dated lines found; is this the AI26 worker log?"
    header = ("| day | cycles | completed | retry | dead | trunc 4k | 8k | 16k | budget lines "
              "| starved | memory dropped | rag dropped |")
    rule = "|" + "---|" * 12
    rows = [header, rule]
    for day in days:
        rows.append(
            f"| {day.date} | {day.cycles} | {day.completed} | {day.retry} | {day.dead} "
            f"| {day.trunc.get('4096', 0)} | {day.trunc.get('8192', 0)} | {day.trunc.get('16384', 0)} "
            f"| {day.budget_lines} | {day.saturated} | {day.omitted.get('memory', 0)} "
            f"| {day.omitted.get('rag', 0)} |"
        )
    total_cycles = sum(d.cycles for d in days)
    total_completed = sum(d.completed for d in days)
    total_budget = sum(d.budget_lines for d in days)
    total_starved = sum(d.saturated for d in days)
    rows.append("")
    if total_cycles:
        rows.append(f"**{total_cycles} cycles, {total_completed} completed "
                    f"({total_completed / total_cycles:.1f} per cycle).**")
    if total_budget:
        rows.append(f"**{total_starved} of {total_budget} prompt builds "
                    f"({100 * total_starved / total_budget:.1f}%) dropped a context section to fit.**")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit AI26 prompt-budget behaviour from the worker log.")
    parser.add_argument("--log", required=True, help="path to the AI26 analysis log")
    parser.add_argument("--days", type=int, default=0, help="only the last N days (0 = all)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    path = Path(args.log)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        print(f"cannot read log: {exc}", file=sys.stderr)
        return 2

    days = audit(lines)
    if args.days > 0:
        days = days[-args.days:]
    if args.json:
        print(json.dumps([d.as_dict() for d in days], indent=2))
    else:
        print(render(days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
