"""Bounded, provenance-labelled prompt assembly for the analysis stages.

Why this module exists
----------------------
Every stage prompt is assembled in :mod:`laclaugpt_data_analysis.context_envelope`
from eight labelled layers (project, source, situational, memory, RAG, the current
source item, the previous analysis and the task). Until now that assembly was
unbounded: ``current_source`` is a lossless JSON dump of the whole canonical record
and ``previous_analysis`` a lossless dump of every earlier stage output, so a large
record produced a prompt larger than the model's context window. The server then
truncated it silently, and because a chat prompt is truncated from the *front* the
first thing lost was the system prompt and the task — the answer stayed fluent while
the instrument had been removed. Nothing in the run log said so.

This module is the shared budget contract that prevents that, ported from the
multimodal pipeline's ``ep24_context_budget`` (issue #372, upstream #241/#262/#285):

* **context is reserved for the answer and for the JSON schema** before any input is
  placed, so a full budget never leaves the model room to answer;
* **every section is capped** and the caps are reported per section, so one huge field
  cannot starve the others;
* **truncation is explicit and per field** — an in-band marker means the model can
  never read a clipped field as a complete one;
* **the model-visible size is logged** before the call instead of being inferred from
  a bad answer afterwards.

It is deliberately pure: it reads no files, contacts no model, and mutates nothing it
is given. Callers keep their own record; only the prompt text is bounded.

This module is infrastructure, not research method. It does not decide what the
analysis says, which sources are evidence, or what any stage asks the model. Changing
a budget changes how much of the *same* instrument fits, never what the instrument is.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: Characters per token used for the estimate. Deliberately crude and stated: it is a
#: *budget signal*, not a tokenizer. A real tokenizer would add a dependency to every
#: stage, and the number exists to catch an over-budget prompt early, not to bill for it.
CHARS_PER_TOKEN = 4

#: In-band marker. A clipped field must never be readable as a complete one.
TRUNCATION_MARKER = "\n[TRUNCATED: field exceeds its prompt budget; the source is unchanged]"

#: Placeholder for a section that kept its header and lost its body to the budget. The
#: section header stays because prompts refer to the eight sections by name.
OMITTED_MARKER = "(omitted: prompt budget exhausted by higher-priority sections)"

TOTAL_ENV = "LACLAUGPT_PROMPT_BUDGET_CHARS"
RESERVE_OUTPUT_ENV = "LACLAUGPT_PROMPT_RESERVE_OUTPUT_CHARS"
RESERVE_SCHEMA_ENV = "LACLAUGPT_PROMPT_RESERVE_SCHEMA_CHARS"
CAP_ENV_PREFIX = "LACLAUGPT_PROMPT_CAP_"

#: A budget below this cannot hold the reserves, the eight headers and anything useful.
MIN_TOTAL_CHARS = 4000

#: Defaults. The structured output path asks Ollama for ``num_ctx`` 16384 tokens; at the
#: crude 4 chars/token ratio that is ~65k characters. 48k total with 6k reserved for the
#: answer and 2k for the JSON shape leaves ~40k of input inside that window, so an
#: ordinary AI26 post is untouched and only an oversize record is bounded. Every number
#: is an environment override; ``LACLAUGPT_PROMPT_BUDGET_CHARS=0`` disables the guard.
DEFAULT_TOTAL = 48_000
DEFAULT_RESERVE_OUTPUT = 6_000
DEFAULT_RESERVE_SCHEMA = 2_000

#: When a caller overrides the total without naming reserves, the reserves keep the same
#: *proportion* as the documented default pair instead of staying absolute. An explicit
#: 8k budget with 6k+2k reserved would otherwise be rejected as unusable, which pushes the
#: caller towards disabling the guard entirely.
RESERVE_OUTPUT_RATIO = DEFAULT_RESERVE_OUTPUT / DEFAULT_TOTAL
RESERVE_SCHEMA_RATIO = DEFAULT_RESERVE_SCHEMA / DEFAULT_TOTAL

_MISSING = ("nan", "none", "nat", "<na>")


class BudgetError(ValueError):
    """The requested budget cannot produce a valid prompt."""


def clean(value: Any) -> str:
    """Normalise a value: missing values and the spellings pandas invents become empty."""
    if value is None:
        return ""
    raw = str(value).strip()
    return "" if raw.lower() in _MISSING else raw


def estimate_tokens(text: str) -> int:
    """Crude token estimate for a budget signal. Empty text is zero tokens, not one."""
    text = clean(text)
    if not text:
        return 0
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


@dataclass(frozen=True, slots=True)
class Section:
    """One labelled input field of a prompt.

    ``header`` is part of the contract, not decoration: it is what tells the model (and
    the reader of the log) where the text came from and what it is not. ``priority``
    decides who keeps the budget; ``cap`` bounds this section regardless of the rest.
    """

    name: str
    header: str
    body: str = ""
    priority: int = 0
    cap: int | None = None

    def cap_for(self, default: int | None) -> int | None:
        if self.cap is not None:
            return int(self.cap)
        env = os.getenv(f"{CAP_ENV_PREFIX}{self.name.upper()}")
        if env not in (None, ""):
            return int(env)
        return default


@dataclass(frozen=True, slots=True)
class FieldReport:
    """What the model actually saw for one section."""

    name: str
    chars: int
    est_tokens: int
    truncated: bool
    omitted: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Packet:
    """The prompt text plus the accounting that makes it auditable."""

    text: str
    report: tuple[FieldReport, ...]
    budget: int
    reserve_output: int
    reserve_schema: int

    @property
    def used(self) -> int:
        return len(self.text)

    @property
    def truncated_fields(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.report if item.truncated)

    @property
    def omitted_fields(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.report if item.omitted)

    def render_report(self) -> str:
        """One compact line per section: chars, estimated tokens, truncation."""
        lines = [
            f"prompt budget: {self.budget} chars "
            f"(reserved: {self.reserve_output} answer + {self.reserve_schema} schema), "
            f"used {self.used}"
        ]
        for item in self.report:
            state = "omitted" if item.omitted else ("truncated" if item.truncated else "full")
            detail = f" ({item.reason})" if item.reason else ""
            lines.append(f"  {item.name}: {item.chars} chars, ~{item.est_tokens} tokens, {state}{detail}")
        return "\n".join(lines)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise BudgetError(f"{name} must be an integer, got {raw!r}") from exc


def _env_int_or_none(name: str) -> int | None:
    raw = os.getenv(name)
    if raw in (None, ""):
        return None
    return _env_int(name, 0)


def resolve_budget(
    total: int | None = None,
    *,
    reserve_output: int | None = None,
    reserve_schema: int | None = None,
) -> tuple[int, int, int]:
    """Resolve the three budget numbers from arguments, then the environment, then defaults.

    A total of ``0`` disables the guard and returns ``(0, 0, 0)``. That is the documented
    escape hatch for a caller that has already bounded its input.
    """
    total = int(total) if total is not None else _env_int(TOTAL_ENV, DEFAULT_TOTAL)
    if total == 0:
        return 0, 0, 0
    if reserve_output is None:
        reserve_output = _env_int_or_none(RESERVE_OUTPUT_ENV)
    if reserve_schema is None:
        reserve_schema = _env_int_or_none(RESERVE_SCHEMA_ENV)
    if reserve_output is None:
        reserve_output = max(1, int(total * RESERVE_OUTPUT_RATIO))
    if reserve_schema is None:
        reserve_schema = max(1, int(total * RESERVE_SCHEMA_RATIO))
    if total < MIN_TOTAL_CHARS:
        raise BudgetError(
            f"prompt budget must be at least {MIN_TOTAL_CHARS} characters, got {total} "
            f"(use 0 to disable budgeting)"
        )
    if reserve_output < 0 or reserve_schema < 0:
        raise BudgetError("reserved answer/schema context cannot be negative")
    if reserve_output + reserve_schema >= total:
        raise BudgetError(
            f"reserved context ({reserve_output} answer + {reserve_schema} schema) leaves no "
            f"room for input within a {total}-character budget; raise {TOTAL_ENV} or lower "
            "the reserves"
        )
    return total, reserve_output, reserve_schema


def allocate(
    sections: Iterable[Section],
    *,
    total: int | None = None,
    reserve_output: int | None = None,
    reserve_schema: int | None = None,
) -> Packet:
    """Assemble a bounded prompt body and report what each section was given.

    Sections are filled by priority (descending), then in the order given. Every header
    is always emitted, so a prompt that names its eight sections still does; a section
    whose body does not fit keeps the header and carries an explicit omitted marker.
    A section that partly fits is truncated with an in-band marker.

    The returned text is guaranteed to be within ``total`` characters, reserves
    included. The caller's data is never modified.
    """
    budget, reserve_output, reserve_schema = resolve_budget(
        total, reserve_output=reserve_output, reserve_schema=reserve_schema
    )
    ordered = sorted(list(sections), key=lambda item: -item.priority)
    if budget == 0:
        text = "\n\n".join(f"{item.header}\n{clean(item.body)}" for item in ordered)
        unbounded = tuple(
            FieldReport(item.name, len(clean(item.body)), estimate_tokens(item.body), False, False)
            for item in ordered
        )
        return Packet(text, unbounded, 0, 0, 0)

    available = budget - reserve_output - reserve_schema
    # Headers, separators and the worst-case omitted markers are fixed costs: reserve
    # them up front so the final text can never exceed the model-visible budget.
    overhead = sum(len(item.header) + 1 for item in ordered) + 2 * max(0, len(ordered) - 1)
    placeholders = len(OMITTED_MARKER) * len(ordered)
    remaining = available - overhead - placeholders

    bodies: dict[str, str] = {}
    report: list[FieldReport] = []
    for item in ordered:
        body = clean(item.body)
        cap = item.cap_for(None)
        if not body:
            bodies[item.name] = ""
            report.append(FieldReport(item.name, 0, 0, False, False))
            continue
        room = remaining if cap is None else min(int(cap), remaining)
        if room <= 0:
            bodies[item.name] = OMITTED_MARKER
            report.append(
                FieldReport(
                    item.name, 0, 0, False, True,
                    "no budget left after higher-priority sections",
                )
            )
            continue
        if len(body) > room:
            keep = max(0, room - len(TRUNCATION_MARKER))
            body = body[:keep] + TRUNCATION_MARKER
            truncated = True
        else:
            truncated = False
        bodies[item.name] = body
        report.append(
            FieldReport(
                item.name, len(body), estimate_tokens(body), truncated, False,
                "exceeds its section cap" if truncated else "",
            )
        )
        remaining -= len(body)

    text = "\n\n".join(f"{item.header}\n{bodies[item.name]}" for item in ordered)
    return Packet(text, tuple(report), budget, reserve_output, reserve_schema)


def prompt_contract_hash(
    prompt: str,
    model: str,
    options: Mapping[str, Any] | None = None,
    *,
    extra: Sequence[Any] = (),
) -> str:
    """A cache key that changes when the prompt, the model OR the options change.

    A cache keyed on the source alone silently reuses answers produced by a different
    prompt or model — the answer looks current and is not. Options are serialised with
    sorted keys so a reordered mapping is the same contract and a changed value is not.
    """
    payload = {
        "prompt": prompt,
        "model": model,
        "options": dict(sorted((options or {}).items())),
        "extra": list(extra),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=repr)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def summarise(packet: Packet) -> dict[str, Any]:
    """Machine-readable accounting for a stage record or a run report."""
    return {
        "budget": packet.budget,
        "reserve_output": packet.reserve_output,
        "reserve_schema": packet.reserve_schema,
        "used": packet.used,
        "est_tokens": estimate_tokens(packet.text),
        "truncated": list(packet.truncated_fields),
        "omitted": list(packet.omitted_fields),
        "sections": [
            {
                "name": item.name,
                "chars": item.chars,
                "est_tokens": item.est_tokens,
                "truncated": item.truncated,
                "omitted": item.omitted,
                "reason": item.reason,
            }
            for item in packet.report
        ],
    }


__all__ = [
    "BudgetError",
    "CAP_ENV_PREFIX",
    "CHARS_PER_TOKEN",
    "DEFAULT_RESERVE_OUTPUT",
    "DEFAULT_RESERVE_SCHEMA",
    "DEFAULT_TOTAL",
    "FieldReport",
    "MIN_TOTAL_CHARS",
    "OMITTED_MARKER",
    "Packet",
    "RESERVE_OUTPUT_ENV",
    "RESERVE_SCHEMA_ENV",
    "Section",
    "TOTAL_ENV",
    "TRUNCATION_MARKER",
    "allocate",
    "clean",
    "estimate_tokens",
    "prompt_contract_hash",
    "resolve_budget",
    "summarise",
]
