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
    if start < 0:
        return None, None
    end = start + len(normalised_quote) - 1
    if end >= len(positions):
        return None, None
    return positions[start], positions[end] + 1


def evidence_ids(record: CanonicalRecord, quotes: list[str], prefix: str) -> list[str]:
    """Attach evidence to a record, verifying each quote against the source.

    Always appends to `record.evidence` (never mutates or removes), and returns
    the new evidence ids so the calling stage can reference them from the objects
    and relations it builds.
    """
    ids: list[str] = []
    source_text = record.content.text or ""
    for quote in quotes:
        text = quote.strip()
        if not text:
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
                metadata={"review_status": "PROVISIONAL", "exact": exact},
            )
        )
        ids.append(evidence_id)
    return ids
