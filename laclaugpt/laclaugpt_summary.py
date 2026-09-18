"""Phase 0 AI26 text summary stage."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import ollama

PROMPT_VERSION = "ai26-phase0-summary-v1"
DEFAULT_SUMMARY_MAX_CHARS = 24000
DEFAULT_SUMMARY_NUM_CTX = 8192
DEFAULT_SUMMARY_NUM_PREDICT = 2048


class SummaryParseError(ValueError):
    """Raised when Ollama returned text that is not valid summary JSON."""

    def __init__(self, message: str, *, raw_response: str, metadata: dict[str, Any]) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.metadata = metadata


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


def _document_label(record: dict[str, Any]) -> str:
    return str(
        record.get("document_id")
        or (record.get("metadata") or {}).get("url")
        or record.get("url")
        or "<unknown>"
    )


def _runtime_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _bounded_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def summarize_record(record: dict[str, Any], normalized_text: str) -> tuple[str, dict[str, Any]]:
    model = os.getenv("OLLAMA_MODEL", "gemma4:12b")
    max_chars = _runtime_int("LACLAUGPT_SUMMARY_MAX_CHARS", DEFAULT_SUMMARY_MAX_CHARS)
    num_ctx = _runtime_int("LACLAUGPT_SUMMARY_NUM_CTX", DEFAULT_SUMMARY_NUM_CTX)
    num_predict = _runtime_int("LACLAUGPT_SUMMARY_NUM_PREDICT", DEFAULT_SUMMARY_NUM_PREDICT)
    bounded_text, truncated = _bounded_text(normalized_text, max_chars)
    request_metadata = {
        "document_id": _document_label(record),
        "original_chars": len(normalized_text),
        "sent_chars": len(bounded_text),
        "truncated": truncated,
        "max_chars": max_chars,
    }
    truncation_note = (
        "\n\n### Input handling\n"
        f"Document was truncated from {len(normalized_text)} to {len(bounded_text)} characters "
        "to stay within the Phase 0 summary context budget."
        if truncated
        else ""
    )
    metadata = record.get("metadata") or {}
    user_prompt = (
        "### Source metadata\n"
        + json.dumps(metadata, ensure_ascii=False, default=str)
        + "\n\n### Document\n"
        + bounded_text
        + truncation_note
    )
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        format="json",
        options={
            "temperature": 0.0,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    )
    raw = response["message"]["content"]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        label = request_metadata["document_id"]
        raise SummaryParseError(
            "Summary JSON parse failed for "
            f"{label} ({len(normalized_text)} chars; sent {len(bounded_text)} chars; "
            f"truncated={truncated}): {exc}",
            raw_response=raw,
            metadata=request_metadata,
        ) from exc

    parsed["model_metadata"] = {
        "provider": "ollama",
        "model": model,
        "num_ctx": num_ctx,
        "num_predict": num_predict,
    }
    parsed["input_metadata"] = request_metadata
    parsed["prompt_version"] = PROMPT_VERSION
    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    return raw, parsed
