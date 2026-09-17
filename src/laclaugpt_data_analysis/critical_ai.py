"""Evidence-first, optional Critical AI Studies analysis.

This module operationalises Critical AI Studies as a provisional qualitative coding
layer. It reuses the canonical prompt envelope, provider abstraction, canonical
Evidence model and model-run provenance rather than creating a parallel framework.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord, Evidence
from .codebooks import CodebookEntry
from .context_envelope import PromptEnvelope, build_prompt_envelope
from .llm.structured_output import chat_structured
from .prompt_library import load_prompt, prompt_provenance

if TYPE_CHECKING:
    from .canonical_pipeline import PipelineContext


CriticalAIDimension = Literal[
    "ideology_shaping_ai",
    "ideology_reproduced_through_ai",
    "ideological_contestation",
    "power_political_economy",
    "labour",
    "data_extraction_coloniality",
    "infrastructure_environment",
    "governance_democracy_surveillance",
    "technological_myths",
    "distribution",
    "alternatives",
    "subjectification",
    "other",
]
FindingStatus = Literal["supported", "tentative", "insufficient_evidence", "not_applicable"]
ReviewStatus = Literal["provisional", "reviewed", "validated", "rejected"]


class CriticalAIObject(BaseModel):
    types: list[
        Literal[
            "model",
            "application",
            "platform",
            "dataset",
            "infrastructure",
            "organisation",
            "labour_process",
            "governance_arrangement",
            "imagined_future",
            "symbolic_signifier",
            "other",
        ]
    ] = Field(default_factory=list)
    description: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class CriticalAISourceEvidence(BaseModel):
    quote_or_span: str
    start: int | None = Field(default=None, ge=0)
    stop: int | None = Field(default=None, ge=0)


class CriticalAIContextSupport(BaseModel):
    prior_analysis_refs: list[str] = Field(default_factory=list)
    project_context_refs: list[str] = Field(default_factory=list)
    rag_refs: list[str] = Field(default_factory=list)
    situational_context_refs: list[str] = Field(default_factory=list)


class CriticalAIInterpretation(BaseModel):
    lens: str = ""
    reasoning_summary: str = ""
    alternative_reading: str | None = None
    missing_evidence: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class CriticalAIReview(BaseModel):
    status: ReviewStatus = "provisional"
    notes: str | None = None


class CriticalAIFinding(BaseModel):
    finding_id: str = ""
    dimension: CriticalAIDimension
    claim: str
    status: FindingStatus = "tentative"
    scope: Literal["source", "actor", "organisation", "system", "discourse", "assemblage"] = (
        "source"
    )
    actors: list[str] = Field(default_factory=list)
    affected_groups: list[str] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    source_evidence: list[CriticalAISourceEvidence] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    context_support: CriticalAIContextSupport = Field(default_factory=CriticalAIContextSupport)
    interpretation: CriticalAIInterpretation = Field(default_factory=CriticalAIInterpretation)
    review: CriticalAIReview = Field(default_factory=CriticalAIReview)


class CriticalAICrossMethod(BaseModel):
    agrees_with_laclau: list[str] = Field(default_factory=list)
    challenges_laclau: list[str] = Field(default_factory=list)
    relevant_dna_statements: list[str] = Field(default_factory=list)
    tensions_or_disagreements: list[str] = Field(default_factory=list)


class CriticalAIAnalysis(BaseModel):
    schema_version: str = "critical-ai-v1"
    prompt_version: str = "v1"
    model: str = ""
    ai_object: CriticalAIObject = Field(default_factory=CriticalAIObject)
    findings: list[CriticalAIFinding] = Field(default_factory=list)
    cross_method: CriticalAICrossMethod = Field(default_factory=CriticalAICrossMethod)
    overall_summary: str = ""
    human_review_priorities: list[str] = Field(default_factory=list)


class CriticalAIConfig(BaseModel):
    """Project-level configuration. Disabled by default, with no pipeline side effects."""

    enabled: bool = False
    provider: str | None = None
    model: str | None = None
    prompt_version: str = "v1"
    include_prior_laclau: bool = True
    include_prior_dna: bool = True
    include_rag: bool = True
    include_periodic_context: bool = True
    evidence_mode: Literal["strict", "balanced"] = "strict"


def critical_ai_config(project_config: dict[str, Any] | None) -> CriticalAIConfig:
    """Read the feature from the existing project-config tree; default is disabled."""
    root = project_config or {}
    analysis = root.get("analysis") if isinstance(root.get("analysis"), dict) else {}
    raw = analysis.get("critical_ai") if isinstance(analysis.get("critical_ai"), dict) else None
    if raw is None and isinstance(root.get("critical_ai"), dict):
        raw = root["critical_ai"]
    return CriticalAIConfig.model_validate(raw or {})


def critical_ai_enabled(project_config: dict[str, Any] | None) -> bool:
    return critical_ai_config(project_config).enabled


def _memory_text(entries: list[CodebookEntry]) -> str:
    rows: list[str] = []
    for entry in entries:
        aliases = ", ".join(entry.aliases)
        rows.append(f"- {entry.kind}: {entry.label}" + (f" (aliases: {aliases})" if aliases else ""))
    return "\n".join(rows)


def _filtered_previous_analysis(record: CanonicalRecord, config: CriticalAIConfig) -> str:
    stages = record.intermediate.stage_outputs
    selected: dict[str, Any] = {}
    always = {
        "preprocess",
        "preprocess_contract",
        "summary_preanalysis",
        "multimodal_synthesis",
        "castells_context",
    }
    for name, value in stages.items():
        folded = name.casefold()
        if name in always:
            selected[name] = value
        elif "discourse" in folded or "laclau" in folded:
            if config.include_prior_laclau:
                selected[name] = value
        elif "dna" in folded:
            if config.include_prior_dna:
                selected[name] = value
    payload = {
        "frame_analysis": record.intermediate.frame_analysis,
        "stage_outputs": selected,
        "human_readable": record.human_readable.model_dump(mode="json"),
        "note": (
            "These are PRIOR_ANALYSIS proposals, not SOURCE_EVIDENCE. "
            "Cross-method disagreement is allowed and should be recorded."
        ),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, indent=2)


def _build_envelope(
    record: CanonicalRecord,
    context: "PipelineContext",
    config: CriticalAIConfig,
    entries: list[CodebookEntry],
    task: str,
) -> PromptEnvelope:
    envelope = build_prompt_envelope(
        record,
        task=task,
        project_context=context.project_context,
        source_context=context.source_context,
        situational_context=(context.situational_context if config.include_periodic_context else ""),
        memory_context="\n".join(
            part for part in (context.memory_context, _memory_text(entries)) if part
        ),
        rag_context=(context.rag_context if config.include_rag else ""),
        context_provenance=context.provenance,
        prompt_version=f"critical-ai:{config.prompt_version}",
    )
    envelope.previous_analysis.text = _filtered_previous_analysis(record, config)
    return envelope


def _append_stage(record: CanonicalRecord, payload: dict[str, Any]) -> None:
    existing = record.intermediate.stage_outputs.get("critical_ai_analysis")
    history = existing if isinstance(existing, list) else ([] if existing is None else [existing])
    history.append(payload)
    record.intermediate.stage_outputs["critical_ai_analysis"] = history


def _project_config_sha256(context: "PipelineContext") -> str:
    if not context.project_config:
        return ""
    payload = json.dumps(context.project_config, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _link_source_evidence(record: CanonicalRecord, analysis: CriticalAIAnalysis) -> None:
    for index, finding in enumerate(analysis.findings, start=1):
        if not finding.finding_id:
            finding.finding_id = f"critical-ai:{index}"
        for source_ev in finding.source_evidence:
            quote = source_ev.quote_or_span.strip()
            if not quote:
                continue
            evidence_id = f"{finding.finding_id}:evidence:{len(finding.evidence_ids) + 1}"
            record.evidence.append(
                Evidence(
                    evidence_id=evidence_id,
                    kind="llm_proposed_source_evidence",
                    source_url=record.source_url,
                    quote=quote,
                    metadata={
                        "analysis_method": "critical_ai_studies",
                        "dimension": finding.dimension,
                        "finding_id": finding.finding_id,
                        "review_status": finding.review.status.upper(),
                        "start": source_ev.start,
                        "stop": source_ev.stop,
                    },
                )
            )
            finding.evidence_ids.append(evidence_id)


def run_optional_critical_ai(
    record: CanonicalRecord,
    *,
    provider,
    context: "PipelineContext",
    codebook_entries: list[CodebookEntry] | None = None,
    model: str = "auto",
    allow_cloud_fallback: bool | None = None,
) -> CriticalAIAnalysis | None:
    """Run Critical AI Studies only when enabled in the existing project settings."""
    config = critical_ai_config(context.project_config)
    if not config.enabled:
        return None

    system_resource = load_prompt("critical_ai.system", version=config.prompt_version)
    task_resource = load_prompt("critical_ai.analysis", version=config.prompt_version)
    rendered_task = task_resource.render(
        evidence_mode=config.evidence_mode,
        include_prior_laclau=str(config.include_prior_laclau).lower(),
        include_prior_dna=str(config.include_prior_dna).lower(),
        include_rag=str(config.include_rag).lower(),
        include_periodic_context=str(config.include_periodic_context).lower(),
    )
    envelope = _build_envelope(
        record,
        context,
        config,
        codebook_entries or [],
        rendered_task.text,
    )
    selected_model = config.model or model
    analysis, response = chat_structured(
        provider,
        CriticalAIAnalysis,
        model=selected_model,
        system_prompt=system_resource.text,
        user_prompt=envelope.render(),
        allow_cloud_fallback=allow_cloud_fallback,
    )
    analysis.prompt_version = config.prompt_version
    analysis.model = response.provenance.actual_model or selected_model
    _link_source_evidence(record, analysis)

    prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
    run_meta = {
        **response.provenance.to_dict(),
        "prompt_version": config.prompt_version,
        "stage": "critical_ai",
        "config_revision": context.config_revision,
        "codebook_revision": context.codebook_revision,
        "context_revision": context.context_revision,
        "project_config_revision": context.project_config_revision,
        "project_config_sha256": _project_config_sha256(context),
        "critical_ai_schema_version": analysis.schema_version,
        "evidence_mode": config.evidence_mode,
        **prompt_meta,
    }
    _append_stage(
        record,
        {
            "created_at": datetime.now(UTC).isoformat(),
            "schema_version": analysis.schema_version,
            "prompt_version": config.prompt_version,
            **prompt_meta,
            "context_provenance": envelope.provenance_snapshot(),
            "configuration": config.model_dump(mode="json"),
            "proposal": analysis.model_dump(mode="json"),
            "model_run": run_meta,
        },
    )
    record.analysis.model_runs.append(run_meta)
    return analysis
