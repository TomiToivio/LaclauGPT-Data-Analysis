"""Runtime relevance selection for researcher-authored codebook context."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from ..codebooks import CodebookEntry

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(value.casefold()) if len(token) > 2}


def _entry_score(query: str, entry: CodebookEntry) -> float:
    """Score one codebook entry against source text without model/network calls."""
    q = query.casefold().strip()
    if not q:
        return 0.0

    labels = [entry.label, *entry.aliases]
    normalized_labels = [label.casefold().strip() for label in labels if label.strip()]
    if any(label in q for label in normalized_labels):
        return 1.0

    q_tokens = _tokens(q)
    entry_tokens = set()
    for value in [*labels, entry.definition]:
        entry_tokens.update(_tokens(value))
    overlap = len(q_tokens & entry_tokens) / max(1, len(entry_tokens))
    fuzzy = max(
        (SequenceMatcher(None, q[:500], label).ratio() for label in normalized_labels),
        default=0.0,
    )
    return max(overlap, fuzzy * 0.5)


def rank_entries(
    query: str,
    entries: list[CodebookEntry],
    *,
    limit: int = 8,
) -> list[tuple[float, CodebookEntry]]:
    scored = [(_entry_score(query, entry), entry) for entry in entries]
    scored.sort(key=lambda item: (-item[0], item[1].kind, item[1].label.casefold()))
    return scored[: max(0, limit)]


def select_relevant_entries(
    query: str,
    entries: list[CodebookEntry],
    *,
    enabled: bool = True,
    limit: int = 8,
    threshold: float = 0.15,
) -> tuple[list[CodebookEntry], dict[str, Any]]:
    """Select only source-relevant codebook concepts and return auditable provenance."""
    ranked = rank_entries(query, entries, limit=limit) if enabled else []
    selected = [(score, entry) for score, entry in ranked if score >= threshold]
    provenance = {
        "enabled": enabled,
        "candidate_count": len(entries),
        "selected_count": len(selected),
        "limit": max(0, limit),
        "threshold": threshold,
        "selection_method": "deterministic_lexical_v1",
        "evidence_role": "context_not_source_evidence",
        "selected": [
            {"kind": entry.kind, "label": entry.label, "score": round(score, 6)}
            for score, entry in selected
        ],
    }
    return [entry for _, entry in selected], provenance


def context_block(
    query: str,
    entries: list[CodebookEntry],
    *,
    limit: int = 8,
    threshold: float = 0.15,
) -> str:
    """Render retrieved candidates explicitly as non-evidentiary researcher context."""
    selected, _ = select_relevant_entries(
        query,
        entries,
        enabled=True,
        limit=limit,
        threshold=threshold,
    )
    if not selected:
        return ""
    header = (
        "Researcher-authored codebook context only. "
        "These concepts are not source evidence and do not prove that the current item expresses them."
    )
    lines = [
        f"- {entry.kind}: {entry.label} | aliases={', '.join(entry.aliases)} | {entry.definition}"
        for entry in selected
    ]
    return "\n".join([header, *lines])
