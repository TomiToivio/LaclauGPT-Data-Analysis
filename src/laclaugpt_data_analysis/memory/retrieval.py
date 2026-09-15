"""Deterministic lexical retrieval and alias resolution."""
from __future__ import annotations

from difflib import SequenceMatcher

from .models import MemoryEntry, Resolution


def resolve(query: str, entries: list[MemoryEntry], *, threshold: float = 0.72) -> Resolution:
    q = query.casefold().strip()
    scored: list[tuple[float, MemoryEntry]] = []
    for entry in entries:
        labels = [entry.canonical_label, *entry.aliases]
        score = max((SequenceMatcher(None, q, label.casefold().strip()).ratio() for label in labels), default=0.0)
        if q in {label.casefold().strip() for label in labels}:
            score = 1.0
        scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1].entry_id))
    candidates = [entry.entry_id for score, entry in scored[:5] if score > 0]
    if not scored or scored[0][0] < threshold:
        return Resolution(query=query, score=scored[0][0] if scored else 0.0,
                          candidates=candidates, abstained=True)
    return Resolution(query=query, entry_id=scored[0][1].entry_id,
                      score=scored[0][0], candidates=candidates)


def context_block(query: str, entries: list[MemoryEntry], *, limit: int = 8) -> str:
    """Return candidates as context, never as source evidence."""
    q = query.casefold()
    ranked = sorted(
        entries,
        key=lambda entry: (
            -(2 if entry.canonical_label.casefold() in q else 0)
            - sum(1 for alias in entry.aliases if alias.casefold() in q),
            entry.entry_id,
        ),
    )[:limit]
    return "\n".join(
        f"- {entry.entry_id}: {entry.canonical_label} | aliases={', '.join(entry.aliases)} | {entry.description}"
        for entry in ranked
    )
