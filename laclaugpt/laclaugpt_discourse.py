"""Phase 0 Us / Frontier / Affect detection.

This replaces binary populism classification with independently reviewable
candidate observations. It deliberately does not answer "is this populist?".
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

import ollama
from pydantic import BaseModel, Field

PROMPT_VERSION = "phase0-us-frontier-affect-v1"


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


SYSTEM_PROMPT = """You are LaclauGPT, a social scientist from the University of Helsinki.

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
    response = ollama.chat(
        model=selected_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
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
        observations.append({
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
        })

    for item in result.frontier_constructs:
        observations.append({
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
        })

    for item in result.affects:
        observations.append({
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
        })

    return observations
