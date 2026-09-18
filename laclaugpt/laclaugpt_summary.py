"""Phase 0 AI26 text summary stage."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import ollama

PROMPT_VERSION = "ai26-phase0-summary-v1"

SYSTEM_PROMPT = """You are LaclauGPT, a social-science research assistant.
Analyze one AI26 RSS/article document conservatively and transparently.
Return JSON only with keys: summary, claims, actors, entities, topics, signifiers,
future_visions, governance_positions, evidence, uncertainty_notes.

Safeguards:
- co-occurrence is not articulation
- difference is not antagonism
- sentiment is not affective investment
- frequency is not hegemony
- one future claim is not a stabilized sociotechnical imaginary
- source or actor identity is not formation evidence
- seed formation metadata is context, not evidence

Use evidence from the current document. Abstain when evidence is weak.
"""


def summarize_record(record: dict[str, Any], normalized_text: str) -> tuple[str, dict[str, Any]]:
    model = os.getenv("OLLAMA_MODEL", "gemma4:12b")
    metadata = record.get("metadata") or {}
    user_prompt = (
        "### Source metadata\n"
        + json.dumps(metadata, ensure_ascii=False, default=str)
        + "\n\n### Document\n"
        + normalized_text
    )
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        format="json",
        options={"temperature": 0.0},
    )
    raw = response["message"]["content"]
    parsed = json.loads(raw)
    parsed["model_metadata"] = {"provider": "ollama", "model": model}
    parsed["prompt_version"] = PROMPT_VERSION
    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    return raw, parsed
