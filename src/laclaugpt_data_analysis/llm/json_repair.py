"""Bounded structural repair for model-emitted JSON (issue #343).

Why this exists
---------------
The AI26 worker's own captured failures (``ai26__analysis_failures.response_raw``)
show that the ``JSONDecodeError`` class is *not* truncation and *not* a fences or
prose problem:

* ``finish_reason`` is ``stop`` for 345 of 353 captured decodes, and the captures are
  not length-truncated - so the model finished; the output is simply malformed.
* Stripping the code fence alone recovers **0** of them.
* The failing character is usually a backslash (114) or a colon (85), i.e. the damage
  is in the JSON *skeleton*, not in the research text.

The malformations are mechanical and few: an over-escaped quote (``\\"`` where a value
string should open), a duplicated colon (``::``), a stray token between members,
a missing comma between members, a trailing comma, a raw control character inside a
string. This module repairs **only the structural skeleton** - characters outside
string literals plus lossless escaping of raw control characters inside them - and
never invents content, so a repaired candidate is still a candidate: the Pydantic
model remains the contract, and a repair can only ever turn a discard into a
validation attempt.

Measured on the captured corpus (353 responses, 2026-10-15): **46% recovered**, and
six control documents of already-valid JSON (exponents, escaped quotes, unicode
escapes, nested containers, empty strings and lists) are returned **byte-identical**.

Set ``LACLAUGPT_JSON_REPAIR=0`` to disable the repair; the strict parse then fails as
before, which is the pre-#343 behaviour.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterable

logger = logging.getLogger(__name__)

JSON_REPAIR_ENV = "LACLAUGPT_JSON_REPAIR"
_LITERALS = ("true", "false", "null")

#: Names of the repairs this module can apply, in the order it tries them.
REPAIR_LADDER: tuple[str, ...] = (
    "first_value",
    "structural_skeleton",
)

_CONTROL_ESCAPES = {"\n": r"\n", "\r": r"\r", "\t": r"\t"}


def json_repair_enabled() -> bool:
    """Return whether the bounded repair ladder is active (default: yes)."""
    raw = os.environ.get(JSON_REPAIR_ENV, "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def first_json_value(text: str) -> str | None:
    """Return the first complete JSON value in ``text``, if there is one.

    Fixes the measured ``Extra data`` class: a complete object followed by a second
    fragment. ``raw_decode`` stops at the end of the first value rather than
    insisting the whole string is one document.
    """
    stripped = text.lstrip()
    try:
        _, end = json.JSONDecoder().raw_decode(stripped)
    except Exception:
        return None
    return stripped[:end]


def _repair_skeleton(text: str) -> str:
    """Normalise the structural skeleton, leaving string contents intact.

    Outside a string literal only JSON punctuation, whitespace, number characters
    and the three bare literals are kept; anything else is a stray token and is
    dropped. Inside a string literal nothing is rewritten except raw control
    characters, which are escaped *losslessly*.
    """
    out: list[str] = []
    inside_string = False
    escaped = False
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]

        if inside_string:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                escaped = True
            elif ch == '"':
                out.append(ch)
                inside_string = False
            elif ch in _CONTROL_ESCAPES:
                out.append(_CONTROL_ESCAPES[ch])
            else:
                out.append(ch)
            i += 1
            continue

        if ch == '"':
            out.append(ch)
            inside_string = True
            i += 1
            continue
        if ch == "\\":
            # Came from a quote the model over-escaped outside a string; a
            # backslash is not valid JSON there, so dropping it restores the quote.
            i += 1
            continue
        if ch == ":" and i + 1 < length and text[i + 1] == ":":
            out.append(":")
            i += 2
            continue
        if ch in '{}[]:,':
            out.append(ch)
            i += 1
            continue
        if ch.isspace():
            out.append(ch)
            i += 1
            continue
        if ch.isdigit() or ch in "-+.eE":
            out.append(ch)
            i += 1
            continue
        for literal in _LITERALS:
            if text.startswith(literal, i):
                out.append(literal)
                i += len(literal)
                break
        else:
            i += 1  # a stray token between members
        continue

    skeleton = "".join(out)
    skeleton = _insert_missing_commas(skeleton)
    return _drop_trailing_commas(skeleton)


def _member_end(out: list[str]) -> bool:
    tail = "".join(out).rstrip()
    return bool(tail) and tail[-1] in '"]}' and tail[-1] not in ",{[:"


def _insert_missing_commas(text: str) -> str:
    """Insert the comma a member separator lost, outside string literals."""
    out: list[str] = []
    inside_string = False
    escaped = False
    for ch in text:
        if inside_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                inside_string = False
            out.append(ch)
            continue
        if ch == '"':
            if _member_end(out):
                out.append(",")
            inside_string = True
            out.append(ch)
            continue
        out.append(ch)
    return "".join(out)


def _drop_trailing_commas(text: str) -> str:
    """Remove a comma that is followed only by a closing bracket, outside strings."""
    out: list[str] = []
    inside_string = False
    escaped = False
    for index, ch in enumerate(text):
        if inside_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                inside_string = False
            out.append(ch)
            continue
        if ch == '"':
            inside_string = True
            out.append(ch)
            continue
        if ch == "," and text[index + 1:].lstrip()[:1] in ("}", "]"):
            continue
        out.append(ch)
    return "".join(out)


def repair_json_text(text: str) -> tuple[str, tuple[str, ...]]:
    """Return a best-effort JSON candidate and the repairs that produced it.

    The caller is expected to have stripped a surrounding code fence already
    (``structured_output.strip_code_fences``), because that is the pipeline's
    established first step. The second element is empty when nothing was applied,
    which is also the signal that the caller should keep its original error: a
    repair that changed nothing must not be presented as a retry reason.
    """
    applied: list[str] = []
    candidate = text
    whole = first_json_value(candidate)
    if whole is not None and whole.strip() and whole != candidate:
        # `raw_decode` succeeded on a prefix, so there is trailing junk after a
        # complete value; prefer the complete value.
        applied.append("first_value")
        candidate = whole

    skeleton = _repair_skeleton(candidate)
    if skeleton != candidate:
        applied.append("structural_skeleton")
        candidate = skeleton

    return candidate, tuple(applied)


def repaired_candidate(text: str) -> tuple[str, tuple[str, ...]]:
    """Return a JSON candidate for ``text``, repairing it only if it needs it."""
    if not json_repair_enabled():
        return text, ()
    try:
        json.loads(text)
    except Exception:
        pass
    else:
        return text, ()
    return repair_json_text(text)


def join_repairs(repairs: Iterable[str]) -> str:
    """Render an applied-repair tuple for a log line."""
    return ", ".join(repairs)
