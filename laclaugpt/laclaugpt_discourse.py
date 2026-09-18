"""Phase 0 Laclaudian discourse analysis for AI26.

Two complementary entry points, deliberately kept in one hand-editable module:

* ``detect_formula_components()`` — the Us / Frontier / Affect pass. Returns typed,
  independently reviewable ``FormulaComponents`` observations. It answers a narrow
  question and never emits a populism verdict.
* ``analyze_discourse()`` — the broader candidate-structure pass used by
  ``laclaugpt_process.py``: signifiers, articulations, demands, chains,
  collective subjects, frontiers, affects, nodal/floating/empty signifier
  candidates, future visions and formation evidence.

Both replace the legacy binary populism classifier. Neither declares a final
theoretical result.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

PROMPT_VERSION = "ai26-phase0-discourse-v2"
DEFAULT_DISCOURSE_MAX_CHARS = 24000
DEFAULT_DISCOURSE_NUM_CTX = 8192
DEFAULT_DISCOURSE_NUM_PREDICT = 2048


class DiscourseParseError(ValueError):
    """Raised when Ollama returned text that is not valid discourse JSON."""

    def __init__(
        self,
        message: str,
        *,
        raw_response: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        # The pipeline always supplies the request metadata, but the field is optional
        # so other callers (and tests) need not fabricate it.
        self.metadata = dict(metadata or {})


class UsConstruct(BaseModel):
    label: str
    text_span: str
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: str = "llm"
    source_date: str | None = None


class FrontierConstruct(BaseModel):
    us_side: str | None = None
    them_side: str
    relation: Literal[
        "opposition",
        "exclusion",
        "antagonistic_boundary",
        "threat_construction",
        "blame",
        "boundary_construction",
    ]
    text_span: str
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: str = "llm"
    source_date: str | None = None


class AffectObservation(BaseModel):
    affect: str
    target: str | None = None
    text_span: str
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: str = "llm"
    source_date: str | None = None


class FormulaComponents(BaseModel):
    us_constructs: list[UsConstruct] = Field(default_factory=list)
    frontier_constructs: list[FrontierConstruct] = Field(default_factory=list)
    affects: list[AffectObservation] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str | None = None


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
- actor/source identity is not formation evidence
"""


FORMULA_SYSTEM_PROMPT = """You are LaclauGPT, a social scientist from the University of Helsinki.

Analyze ONLY three independent discourse-theoretical components:
1. Us constructions
2. Frontiers / antagonistic boundaries
3. Affect / affective investment

Do NOT classify the document, actor, statement or discourse as populist or not populist.
Do NOT output any populism score.

Us construction:
- identify politically meaningful collective subjects such as "we", "workers", "citizens",
  "humanity", "researchers", "developers", etc.
- do not treat every plural pronoun as meaningful
- preserve a short source span

Frontier:
- detect a meaningful relational boundary, opposition, exclusion, threat, blame relation,
  or antagonistic construction between an Us/position and an outside/opponent/obstacle
- negative sentiment alone is not a frontier
- the Us side may be absent if the text constructs only an opponent/boundary

Affect:
- identify affective investment or affective expressions such as fear, anger, hope,
  enthusiasm, anxiety, resentment, pride, urgency
- affect is not generic sentiment
- preserve the target when supported

Return JSON only and conform exactly to the supplied schema.
If evidence is weak, return an empty list or a low-confidence candidate.
"""


def detect_formula_components(
    text: str,
    *,
    source_date: str | None = None,
    model: str | None = None,
) -> tuple[str, FormulaComponents]:
    selected_model = model or os.getenv("OLLAMA_MODEL", "gemma4:12b")
    schema = FormulaComponents.model_json_schema()
    response = _ollama().chat(
        model=selected_model,
        messages=[
            {"role": "system", "content": FORMULA_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        format=schema,
        options={"temperature": 0.0},
    )
    raw = response["message"]["content"]
    parsed = FormulaComponents.model_validate_json(raw)

    for item in parsed.us_constructs:
        item.source_date = source_date
    for item in parsed.frontier_constructs:
        item.source_date = source_date
    for item in parsed.affects:
        item.source_date = source_date

    parsed.model_metadata = {"provider": "ollama", "model": selected_model}
    parsed.generated_at = datetime.now(timezone.utc).isoformat()
    return raw, parsed


def to_graph_observations(
    result: FormulaComponents,
    *,
    source_url: str,
    document_id: str | None = None,
) -> list[dict[str, Any]]:
    """Project component observations into simple shared graph-friendly records."""
    observations: list[dict[str, Any]] = []

    for item in result.us_constructs:
        observations.append(
            {
                "kind": "us_construct",
                "subject": item.label,
                "predicate": "constructs_us",
                "object": item.label,
                "source_url": source_url,
                "document_id": document_id,
                "source_date": item.source_date,
                "text_span": item.text_span,
                "confidence": item.confidence,
                "provenance": item.provenance,
            }
        )

    for item in result.frontier_constructs:
        observations.append(
            {
                "kind": "frontier_construct",
                "subject": item.us_side,
                "predicate": item.relation,
                "object": item.them_side,
                "source_url": source_url,
                "document_id": document_id,
                "source_date": item.source_date,
                "text_span": item.text_span,
                "confidence": item.confidence,
                "provenance": item.provenance,
            }
        )

    for item in result.affects:
        observations.append(
            {
                "kind": "affect",
                "subject": item.target,
                "predicate": "expresses_affect",
                "object": item.affect,
                "source_url": source_url,
                "document_id": document_id,
                "source_date": item.source_date,
                "text_span": item.text_span,
                "confidence": item.confidence,
                "provenance": item.provenance,
            }
        )

    return observations


CANDIDATE_STRUCTURES_PROMPT = SYSTEM_PROMPT


def _ollama():
    import ollama
    return ollama


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


def analyze_discourse(
    record: dict[str, Any],
    normalized_text: str,
    summary: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    model = os.getenv("OLLAMA_MODEL", "gemma4:12b")
    max_chars = _runtime_int("LACLAUGPT_DISCOURSE_MAX_CHARS", DEFAULT_DISCOURSE_MAX_CHARS)
    num_ctx = _runtime_int("LACLAUGPT_DISCOURSE_NUM_CTX", DEFAULT_DISCOURSE_NUM_CTX)
    num_predict = _runtime_int("LACLAUGPT_DISCOURSE_NUM_PREDICT", DEFAULT_DISCOURSE_NUM_PREDICT)
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
        "to stay within the Phase 0 discourse context budget."
        if truncated
        else ""
    )
    user_prompt = (
        "### Current document\n"
        + bounded_text
        + truncation_note
        + "\n\n### Prior summary\n"
        + json.dumps(summary, ensure_ascii=False, default=str)
    )
    response = _ollama().chat(
        model=model,
        messages=[
            {"role": "system", "content": CANDIDATE_STRUCTURES_PROMPT},
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
        raise DiscourseParseError(
            "Discourse JSON parse failed for "
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
