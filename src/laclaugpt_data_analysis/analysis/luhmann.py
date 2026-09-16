"""Experimental Luhmann/Social Systems analysis helpers.

This module is deliberately optional and theory-aware. It provides structured
result schemas, a transparent non-LLM prototype classifier, basic information-
theoretic measures, and cross-system graph materialization. It does not treat
measured features as proof of autopoiesis or self-organization.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


class EvidenceSpan(BaseModel):
    text: str
    start: int | None = None
    end: int | None = None
    source_record_id: str | None = None


class Candidate(BaseModel):
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)


class CrossSystemTranslation(BaseModel):
    source_system: str
    target_system: str
    relation: str = "translated_as"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)


class SystemsAnalysis(BaseModel):
    primary_system: str | None = None
    referenced_systems: list[str] = Field(default_factory=list)
    organization_context: str | None = None
    system_environment_distinction: str | None = None
    communication_code_candidates: list[Candidate] = Field(default_factory=list)
    programme_or_criterion_candidates: list[Candidate] = Field(default_factory=list)
    structural_couplings: list[CrossSystemTranslation] = Field(default_factory=list)
    cross_system_translations: list[CrossSystemTranslation] = Field(default_factory=list)
    observations_of_other_systems: list[str] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    model_method: str = "unassigned"
    provenance: dict[str, Any] = Field(default_factory=dict)
    human_validation: str = "unreviewed"


class FunctionalSystemDefinition(BaseModel):
    id: str
    label: str
    definition: str
    prototype_terms: list[str] = Field(default_factory=list)
    code_candidates: list[str] = Field(default_factory=list)
    programme_candidates: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class LuhmannCodebook(BaseModel):
    version: str
    theory: str = "Luhmann social systems"
    uncertainty_policy: list[str] = Field(default_factory=list)
    systems: list[FunctionalSystemDefinition]

    def system(self, system_id: str) -> FunctionalSystemDefinition:
        for item in self.systems:
            if item.id == system_id:
                return item
        raise KeyError(system_id)


class SystemScore(BaseModel):
    system: str
    score: float = Field(ge=0.0, le=1.0)
    matched_terms: list[str] = Field(default_factory=list)


def load_codebook(path: str | Path) -> LuhmannCodebook:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Luhmann codebook must contain a mapping")
    return LuhmannCodebook.model_validate(raw)


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(text)}


def prototype_classify(
    text: str,
    codebook: LuhmannCodebook,
    *,
    top_k: int = 3,
    minimum_score: float = 0.01,
) -> list[SystemScore]:
    """Transparent non-LLM baseline based on normalized prototype-term overlap.

    This is intentionally modest: it provides a reproducible comparison baseline,
    not a theoretically sufficient operationalization of functional differentiation.
    """
    doc_tokens = _tokens(text)
    scores: list[SystemScore] = []
    for system in codebook.systems:
        term_tokens: set[str] = set()
        matched_terms: list[str] = []
        for term in system.prototype_terms:
            tokens = _tokens(term)
            term_tokens.update(tokens)
            if tokens and tokens.issubset(doc_tokens):
                matched_terms.append(term)
        if not term_tokens:
            continue
        overlap = len(doc_tokens & term_tokens)
        denominator = math.sqrt(max(len(doc_tokens), 1) * len(term_tokens))
        score = overlap / denominator if denominator else 0.0
        if score >= minimum_score:
            scores.append(
                SystemScore(
                    system=system.id,
                    score=min(score, 1.0),
                    matched_terms=matched_terms,
                )
            )
    return sorted(scores, key=lambda item: (-item.score, item.system))[:top_k]


def baseline_to_analysis(
    text: str,
    codebook: LuhmannCodebook,
    *,
    source_record_id: str | None = None,
) -> SystemsAnalysis:
    scores = prototype_classify(text, codebook)
    if not scores:
        return SystemsAnalysis(
            primary_system="unknown",
            model_method="prototype-term-overlap-v1",
            provenance={"codebook_version": codebook.version, "source_record_id": source_record_id},
        )
    primary = scores[0]
    referenced = [item.system for item in scores]
    confidence = primary.score
    return SystemsAnalysis(
        primary_system=primary.system,
        referenced_systems=referenced,
        confidence=confidence,
        model_method="prototype-term-overlap-v1",
        provenance={
            "codebook_version": codebook.version,
            "source_record_id": source_record_id,
            "baseline_scores": [item.model_dump() for item in scores],
        },
    )


def build_structured_extraction_prompt(text: str, codebook: LuhmannCodebook) -> str:
    """Build a conservative prompt for any structured-output LLM adapter.

    The caller is responsible for model invocation. The returned prompt explicitly
    permits unknown/mixed interpretations and asks for source-grounded evidence.
    """
    systems = "\n".join(
        f"- {item.id}: {item.definition}" for item in codebook.systems
    )
    return (
        "Analyze the communication using the supplied Luhmann/Social Systems codebook. "
        "Do not force a single functional-system label. Use unknown or multiple references "
        "when evidence is weak or mixed. Treat codes/programmes as candidates, not universal "
        "fixed binaries. Every substantive interpretation should be tied to evidence spans.\n\n"
        f"Supported systems:\n{systems}\n\n"
        "Return JSON matching the SystemsAnalysis schema.\n\n"
        f"TEXT:\n{text}"
    )


def parse_structured_analysis(payload: Mapping[str, Any]) -> SystemsAnalysis:
    return SystemsAnalysis.model_validate(payload)


def shannon_entropy(values: Iterable[str]) -> float:
    counts = Counter(values)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def mutual_information(pairs: Iterable[tuple[str, str]]) -> float:
    observed = list(pairs)
    total = len(observed)
    if total == 0:
        return 0.0
    joint = Counter(observed)
    left = Counter(a for a, _ in observed)
    right = Counter(b for _, b in observed)
    score = 0.0
    for (a, b), n_ab in joint.items():
        p_ab = n_ab / total
        p_a = left[a] / total
        p_b = right[b] / total
        score += p_ab * math.log2(p_ab / (p_a * p_b))
    return score


def contingency_matrix(
    pairs: Iterable[tuple[str, str]],
) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for left, right in pairs:
        matrix[left][right] += 1
    return {left: dict(row) for left, row in matrix.items()}


def translation_edges(
    analyses: Sequence[tuple[str, SystemsAnalysis]],
) -> list[dict[str, Any]]:
    """Materialize evidence-preserving cross-system graph edges.

    ``analyses`` contains ``(source_record_id, analysis)`` pairs. Returned rows can
    be exported to NetworkX/igraph/knowledge-graph adapters downstream.
    """
    rows: list[dict[str, Any]] = []
    for source_record_id, analysis in analyses:
        for edge in analysis.cross_system_translations:
            rows.append(
                {
                    "source_record_id": source_record_id,
                    "source_system": edge.source_system,
                    "target_system": edge.target_system,
                    "relation": edge.relation,
                    "confidence": edge.confidence,
                    "evidence_spans": [span.model_dump() for span in edge.evidence_spans],
                    "model_method": analysis.model_method,
                    "provenance": analysis.provenance,
                }
            )
    return rows
