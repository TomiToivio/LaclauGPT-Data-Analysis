"""Runtime context retrieval over versioned codebook entries."""
from __future__ import annotations

from difflib import SequenceMatcher

from ..codebooks import CodebookEntry


def rank_entries(query: str, entries: list[CodebookEntry], *, limit: int = 8) -> list[tuple[float, CodebookEntry]]:
    q = query.casefold().strip()
    scored: list[tuple[float, CodebookEntry]] = []
    for entry in entries:
        labels = [entry.label, *entry.aliases]
        score = max((SequenceMatcher(None, q, label.casefold()).ratio() for label in labels), default=0.0)
        if any(label.casefold() in q for label in labels):
            score = max(score, 0.95)
        scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1].kind, item[1].label.casefold()))
    return scored[:limit]


def context_block(query: str, entries: list[CodebookEntry], *, limit: int = 8, threshold: float = 0.15) -> str:
    """Render retrieved candidates as non-evidentiary context."""
    ranked = [(score, entry) for score, entry in rank_entries(query, entries, limit=limit) if score >= threshold]
    if not ranked:
        return ""
    return "\n".join(
        f"- {entry.kind}: {entry.label} | aliases={', '.join(entry.aliases)} | {entry.definition}"
        for _, entry in ranked
    )
