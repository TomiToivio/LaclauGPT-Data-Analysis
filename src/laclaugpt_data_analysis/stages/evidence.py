"""Evidence verification: turning a model's quotations into checkable evidence.

This module carries the pipeline's central integrity rule:

    A model-proposed quotation counts as evidence only when the code can point
    at it in the source text.

Everything else in the pipeline is a *proposal*. Evidence is the one thing the
code itself can verify, so it is verified here and nowhere else — every stage
that cites evidence routes through these two functions.

Policy: flag-and-count, never silent drop
-----------------------------------------
When a quote *is* found, the evidence carries real character offsets and
`exact=True`. When it is *not*, the evidence is still recorded, with
`exact=False` and no offsets. Dropping non-verbatim quotes would hide the rate at
which the model paraphrases instead of quoting — which is itself a finding about
the model's reliability, and part of the audit trail a reviewer needs.

The minimum length rule
-----------------------
Quotes shorter than `_MIN_QUOTE_CHARS` are refused even when they match: a very
short string occurs by chance in almost any text, and letting one pass would
allow a stray fragment to masquerade as a substantiated quotation.
"""
from __future__ import annotations

import re

from ..canonical import CanonicalRecord, Evidence
from .proposals import _MIN_QUOTE_CHARS


def locate_quote(source_text: str, quote: str) -> tuple[int | None, int | None]:
    """Locate `quote` in `source_text`, tolerant of whitespace differences.

    Returns `(start, end)` offsets into `source_text` when the quote occurs
    verbatim (whitespace-normalised), otherwise `(None, None)`.

    Models re-wrap and collapse whitespace, so an exact string match alone would
    reject genuine quotations. The normalised index maps each normalised
    character back to its offset in the ORIGINAL text, so the returned span still
    slices the source as written.
    """
    if not source_text or not quote:
        return None, None
    if len(quote.strip()) < _MIN_QUOTE_CHARS:
        return None, None

    # Direct hit first: the cheap, exact case.
    exact_start = source_text.find(quote)
    if exact_start >= 0:
        return exact_start, exact_start + len(quote)

    normalised_chars: list[str] = []
    positions: list[int] = []
    previous_space = False
    for index, char in enumerate(source_text):
        if char.isspace():
            if previous_space:
                continue
            normalised_chars.append(" ")
            positions.append(index)
            previous_space = True
        else:
            normalised_chars.append(char.lower())
            positions.append(index)
            previous_space = False
    normalised_source = "".join(normalised_chars)
    normalised_quote = " ".join(quote.split()).lower()
    if not normalised_quote:
        return None, None

    start = normalised_source.find(normalised_quote)
    if start >= 0:
        end = start + len(normalised_quote) - 1
        if end >= len(positions):
            return None, None
        return positions[start], positions[end] + 1

    return _locate_elided(normalised_source, normalised_quote, positions)


_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|\u2026)\s*")


def _locate_elided(normalised_source: str, normalised_quote: str,
                   positions: list[int]) -> tuple[int | None, int | None]:
    """Match a quote the model joined across a gap, e.g. "first words... last words".

    Models elide the middle of a long passage rather than quoting it whole. Treating that as a
    fabrication understates grounding: 11.9 % of sampled quotations carry an ellipsis. Each segment
    must still occur, in order, and be long enough not to match by chance — so this recovers real
    quotations without accepting paraphrase.
    """
    segments = [segment for segment in _ELLIPSIS.split(normalised_quote)
                if len(segment) >= _MIN_QUOTE_CHARS]
    if len(segments) < 2:
        return None, None
    cursor = 0
    first: int | None = None
    last: int | None = None
    for segment in segments:
        found = normalised_source.find(segment, cursor)
        if found < 0:
            return None, None
        if first is None:
            first = found
        last = found + len(segment) - 1
        cursor = found + len(segment)
    if first is None or last is None or last >= len(positions):
        return None, None
    return positions[first], positions[last] + 1


# #458 / D6: the model may decline to quote; that is a result, not a citation.
VERBATIM_ABSTENTION = "no verbatim evidence found"


def is_abstention(quote: str) -> bool:
    """True when the model declined instead of quoting."""
    return quote.strip().casefold().startswith(VERBATIM_ABSTENTION)


def evidence_status(exact: bool) -> str:
    """Per-item status stored alongside `exact`; additive to the existing metrics."""
    return "verified" if exact else "unverified"


def evidence_ids(record: CanonicalRecord, quotes: list[str], prefix: str) -> list[str]:
    """Attach evidence to a record, verifying each quote against the source.

    Always appends to `record.evidence` (never mutates or removes), and returns
    the new evidence ids so the calling stage can reference them from the objects
    and relations it builds.
    """
    # A quotation match establishes textual presence, not who endorsed the words.
    # A journalist can report a minister's articulation without sharing it.
    # Check speaker and context (paper §3.4; docs/methods/phase1_researcher_guide.md).
    ids: list[str] = []
    source_text = record.content.text or ""
    for quote in quotes:
        text = quote.strip()
        if not text or is_abstention(text):
            # A stored abstention would be counted as a citation by every downstream
            # metric; the object keeps its analysis, the evidence list keeps its honesty.
            continue
        evidence_id = f"{prefix}:evidence:{len(record.evidence) + 1}"
        start, end = locate_quote(source_text, text)
        exact = start is not None and end is not None
        record.evidence.append(
            Evidence(
                evidence_id=evidence_id,
                kind="llm_proposed_source_evidence",
                source_url=record.source_url,
                quote=text,
                start_offset=start if exact else None,
                end_offset=end if exact else None,
                metadata={
                    "review_status": "PROVISIONAL",
                    "exact": exact,
                    "evidence_status": evidence_status(exact),
                },
            )
        )
        ids.append(evidence_id)
    return ids
