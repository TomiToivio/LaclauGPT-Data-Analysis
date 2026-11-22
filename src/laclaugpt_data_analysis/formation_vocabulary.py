"""AI26 formation labels: a small, explicit, versioned aggregation vocabulary.

Only exact, publicly documented codebook aliases are normalized. Novel prose is
not inferred into an ideology. It becomes an unresolved candidate with its
original wording preserved in the description/metadata for human review.
These categories remain PROVISIONAL and never assert a person's ideology.
"""
from __future__ import annotations

import re

FORMATION_VOCABULARY_VERSION = "ai26-formations-2026-11-22"
FORMATION_LABELS = frozenset(
    {
        "existential_risk",
        "accelerationist",
        "left_accelerationist",
        "ai_safety",
        "critical_ai",
        "anti_ai",
    }
)
FORMATION_FALLBACKS = frozenset({"other", "unknown"})

_ALIASES: dict[str, str] = {
    "existential_risk": "existential_risk",
    "existential risk": "existential_risk",
    "doomerism": "existential_risk",
    "ai doomerism": "existential_risk",
    "x-risk": "existential_risk",
    "accelerationist": "accelerationist",
    "accelerationism": "accelerationist",
    "e/acc": "accelerationist",
    "left_accelerationist": "left_accelerationist",
    "left accelerationist": "left_accelerationist",
    "left-wing accelerationism": "left_accelerationist",
    "left techno-optimism": "left_accelerationist",
    "post-work techno-optimism": "left_accelerationist",
    "ai_safety": "ai_safety",
    "ai safety": "ai_safety",
    "ai safety discourse": "ai_safety",
    "alignment discourse": "ai_safety",
    "critical_ai": "critical_ai",
    "critical ai": "critical_ai",
    "ai critical": "critical_ai",
    "critical ai studies": "critical_ai",
    "anti_ai": "anti_ai",
    "anti-ai": "anti_ai",
    "ai opposition": "anti_ai",
    "anti_ai_protest": "anti_ai",
    "other": "other",
    "unknown": "unknown",
}
# Ambiguous contextual terms (e.g. techno-optimism, pause_ai) deliberately
# have no automatic mapping: context may distinguish different formations.

def normalize_formation_label(label: str) -> tuple[str, bool]:
    """Return the controlled label and whether it matches a documented alias."""
    text = re.sub(r"\s+", " ", label.strip()).casefold()
    normalized = _ALIASES.get(text)
    if normalized:
        return normalized, True
    return "unknown", False


def is_countable_formation(item: object) -> bool:
    """Exclude unresolved non-formations from counts, filters and distributions.

    Legacy labels without the new metadata remain visible as historical data;
    neither 'unknown' nor 'other' is an ideological formation in any version.
    """
    label = str(getattr(item, "label", "") or "").strip().casefold()
    metadata = getattr(item, "metadata", None) or {}
    return bool(
        label
        and label not in FORMATION_FALLBACKS
        and metadata.get("formation_label_resolved") is not False
    )
