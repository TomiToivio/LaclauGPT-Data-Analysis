"""Phase 0 AI26 text summary stage."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import ollama

PROMPT_VERSION = "ai26-phase0-summary-v1"

# Input/context bounds for the summary call. This stage runs *before* every other LLM
# stage, so an unbounded document here blocks the whole document. Real AI26 sources
# reach ~130k characters (~32k tokens), far beyond gemma4:12b's window, which produced
# empty responses and a bare "Expecting value: line 1 column 1 (char 0)" (#225). Mirrors
# the discourse stage's bounds.
DEFAULT_SUMMARY_MAX_CHARS = 24000
DEFAULT_SUMMARY_NUM_CTX = 8192
DEFAULT_SUMMARY_NUM_PREDICT = 2048
DEFAULT_SUMMARY_EMPTY_RETRIES = 2


class SummaryParseError(ValueError):
    """Raised when Ollama returned text that is not valid summary JSON."""

    def __init__(
        self,
        message: str,
        *,
        raw_response: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.metadata = dict(metadata or {})


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
        or record.get("source_url")
        or record.get("url")
        or "<unknown>"
    )


def _runtime_int(name: str, default: int) -> int:
    """Resolve an integer setting at call time, so a running process can be tuned."""
    return int(os.getenv(name, str(default)))


def _bounded_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Cap the document text sent to the model; report whether truncation happened."""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def summarize_record(record: dict[str, Any], normalized_text: str) -> tuple[str, dict[str, Any]]:
    model = os.getenv("OLLAMA_MODEL", "gemma4:12b")
    max_chars = _runtime_int("LACLAUGPT_SUMMARY_MAX_CHARS", DEFAULT_SUMMARY_MAX_CHARS)
    num_ctx = _runtime_int("LACLAUGPT_SUMMARY_NUM_CTX", DEFAULT_SUMMARY_NUM_CTX)
    num_predict = _runtime_int("LACLAUGPT_SUMMARY_NUM_PREDICT", DEFAULT_SUMMARY_NUM_PREDICT)
    empty_retries = _runtime_int(
        "LACLAUGPT_SUMMARY_EMPTY_RETRIES", DEFAULT_SUMMARY_EMPTY_RETRIES
    )
    if empty_retries < 0:
        raise ValueError("LACLAUGPT_SUMMARY_EMPTY_RETRIES must be >= 0")

    bounded_text, truncated = _bounded_text(normalized_text, max_chars)
    request_metadata = {
        "document_id": _document_label(record),
        "original_chars": len(normalized_text),
        "sent_chars": len(bounded_text),
        "truncated": truncated,
        "max_chars": max_chars,
    }
    metadata = record.get("metadata") or {}
    truncation_note = (
        "\n\n### Input handling\n"
        f"Document was truncated from {len(normalized_text)} to {len(bounded_text)} characters "
        "to stay within the Phase 0 summary context budget."
        if truncated
        else ""
    )
    user_prompt = (
        "### Source metadata\n"
        + json.dumps(metadata, ensure_ascii=False, default=str)
        + "\n\n### Document\n"
        + bounded_text
        + truncation_note
    )

    raw = ""
    attempts = 0
    empty_responses = 0
    max_attempts = empty_retries + 1
    while attempts < max_attempts:
        attempts += 1
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
        if raw.strip():
            break
        empty_responses += 1

    request_metadata["attempt_count"] = attempts
    request_metadata["empty_response_count"] = empty_responses
    # "Retries" = calls after the first. Deriving this from empty_responses under-counts
    # when a retry succeeds (empty, empty, good => 2 retries, not 1), which is exactly the
    # case an operator wants to see when diagnosing a slow document (#234).
    request_metadata["empty_retry_count"] = max(0, attempts - 1)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        label = request_metadata["document_id"]
        raise SummaryParseError(
            "Summary JSON parse failed for "
            f"{label} ({len(normalized_text)} chars; sent {len(bounded_text)} chars; "
            f"truncated={truncated}; attempts={attempts}): {exc}",
            raw_response=raw,
            metadata=request_metadata,
        ) from exc

    if not isinstance(parsed, dict):
        label = request_metadata["document_id"]
        raise SummaryParseError(
            "Summary JSON must be an object for "
            f"{label}; got {type(parsed).__name__}",
            raw_response=raw,
            metadata=request_metadata,
        )

    parsed["model_metadata"] = {
        "provider": "ollama",
        "model": model,
        "num_ctx": num_ctx,
        "num_predict": num_predict,
    }
    parsed["prompt_version"] = PROMPT_VERSION
    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    parsed["input_metadata"] = request_metadata
    return raw, parsed
