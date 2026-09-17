"""Generic, privacy-safe Hungary26 old-vs-new comparison helpers."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

DIMENSIONS = (
    "entity_resolution",
    "theme_normalization",
    "source_speaker_attribution",
    "hungarian_asr",
    "translation_preservation",
    "multimodal_evidence_coverage",
    "splitting_context_preservation",
    "unsupported_interpretations",
    "laclau_claim_grounding",
    "uncertainty_abstention",
    "provenance_completeness",
    "near_duplicate_consistency",
    "researcher_usefulness",
)


def _analysis(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("analysis", {})
    return value if isinstance(value, dict) else {}


def _evidence_count(payload: dict[str, Any]) -> int:
    value = payload.get("evidence", [])
    return len(value) if isinstance(value, list) else 0


def _provenance_count(payload: dict[str, Any]) -> int:
    value = payload.get("provenance", [])
    return len(value) if isinstance(value, list) else 0


def compare_pair(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Return inspectable indicators, never an automatic 'new is better' verdict."""
    old_a, new_a = _analysis(old), _analysis(new)
    old_entities = old_a.get("entities", []) if isinstance(old_a.get("entities", []), list) else []
    new_entities = new_a.get("entities", []) if isinstance(new_a.get("entities", []), list) else []
    old_themes = old_a.get("themes", []) if isinstance(old_a.get("themes", []), list) else []
    new_themes = new_a.get("themes", []) if isinstance(new_a.get("themes", []), list) else []
    return {
        "source_url": new.get("source_url") or old.get("source_url") or "",
        "indicators": {
            "entity_count_old": len(old_entities),
            "entity_count_new": len(new_entities),
            "theme_count_old": len(old_themes),
            "theme_count_new": len(new_themes),
            "evidence_count_old": _evidence_count(old),
            "evidence_count_new": _evidence_count(new),
            "provenance_count_old": _provenance_count(old),
            "provenance_count_new": _provenance_count(new),
            "uncertainty_count_old": len(old_a.get("uncertainty", []) or []),
            "uncertainty_count_new": len(new_a.get("uncertainty", []) or []),
            "abstention_count_old": len(old_a.get("abstentions", []) or []),
            "abstention_count_new": len(new_a.get("abstentions", []) or []),
        },
        "review_dimensions": list(DIMENSIONS),
        "human_review_required": True,
        "guardrail": "Do not infer quality from output length or theoretical elaboration.",
    }


def aggregate_comparison(pairs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(pairs)
    totals: Counter[str] = Counter()
    for row in rows:
        for key, value in row.get("indicators", {}).items():
            if isinstance(value, int):
                totals[key] += value
    return {
        "schema_version": "hungary26-pilot-comparison-v1",
        "records": len(rows),
        "indicator_totals": dict(totals),
        "review_dimensions": list(DIMENSIONS),
        "human_review_required": True,
    }
