"""Phase 0 Laclaudian discourse analysis for AI26."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import ollama

PROMPT_VERSION = "ai26-phase0-discourse-v1"

SYSTEM_PROMPT = """You are LaclauGPT, a social scientist doing cautious Laclau/Mouffe/Palonen-inspired discourse analysis.
Return JSON only. Identify candidate relational structures, never final theoretical facts.

Required keys:
signifiers, articulations, demands, chains_equivalence, chains_difference,
collective_subjects, frontiers, affects, nodal_point_candidates,
floating_signifier_candidates, empty_signifier_candidates,
future_vision_candidates, formation_evidence, counter_evidence, uncertainty_notes.

Rules:
- never output populism true/false
- Us/frontier/affect are candidate structures and require textual evidence
- disagreement or negative sentiment is not automatically antagonism
- sentiment is not affective investment
- frequency is not hegemony
- polysemy alone is not floating/empty signification
- one future claim is not a stabilized sociotechnical imaginary
- formation labels are provisional context only
- allow overlap, contradiction, unknown and abstention
- actor/source identity is not formation evidence
"""


def analyze_discourse(record: dict[str, Any], normalized_text: str, summary: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    model = os.getenv("OLLAMA_MODEL", "gemma4:12b")
    user_prompt = (
        "### Current document\n"
        + normalized_text
        + "\n\n### Prior summary\n"
        + json.dumps(summary, ensure_ascii=False, default=str)
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
