"""Optional evidence-linked Discourse Network Analyzer statement coding.

The stage proposes DNA-compatible actor-concept statements from a CanonicalRecord while
reusing the repository's canonical DiscourseStatement. It is disabled by default and
keeps LLM output provisional for human review.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, model_validator

from .canonical import CanonicalRecord
from .codebooks import CodebookEntry
from .context_envelope import PromptEnvelope, build_prompt_envelope
from .discourse_network.models import DiscourseStatement, EvidenceSpan, Stance, ValidationStatus
from .llm.structured_output import chat_structured
from .prompt_library import load_prompt, prompt_provenance

if TYPE_CHECKING:
    from .canonical_pipeline import PipelineContext


AgreementStatus = Literal["coded", "ambiguous", "not_applicable", "abstain"]
ConceptMode = Literal["codebook_or_provisional", "codebook_only", "open"]
DuplicatePolicy = Literal["preserve", "collapse_document_actor_concept_agreement"]


class DNAEntityCandidate(BaseModel):
    id: str | None = None
    label: str | None = None


class DNAConceptCandidate(BaseModel):
    id: str | None = None
    label: str
    original_text: str | None = None
    provisional: bool = False
    mapping_confidence: float | None = Field(default=None, ge=0, le=1)


class DNAStatementCandidate(BaseModel):
    person: DNAEntityCandidate | None = None
    organization: DNAEntityCandidate | None = None
    concept: DNAConceptCandidate
    agreement: bool | None = None
    agreement_status: AgreementStatus = "abstain"
    evidence_text: str
    start: int | None = Field(default=None, ge=0)
    stop: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    uncertainty_reason: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_actor_and_agreement(self) -> "DNAStatementCandidate":
        person = self.person.label.strip() if self.person and self.person.label else ""
        organisation = (
            self.organization.label.strip() if self.organization and self.organization.label else ""
        )
        if not person and not organisation:
            raise ValueError("DNA statement requires a person or organization speaker")
        if self.agreement_status == "coded" and self.agreement is None:
            raise ValueError("coded agreement requires true or false")
        if self.agreement_status != "coded" and self.agreement is not None:
            raise ValueError("non-coded agreement must be null")
        return self


class DNAStatementBatch(BaseModel):
    schema_version: str = "dna-statement-coding-v1"
    statements: list[DNAStatementCandidate] = Field(default_factory=list)
    abstentions: list[str] = Field(default_factory=list)


class DNAStatementCodingConfig(BaseModel):
    """Project-level DNA statement coding configuration; disabled by default."""

    enabled: bool = False
    provider: str | None = None
    model: str | None = None
    prompt_version: str = "v1"
    concept_mode: ConceptMode = "codebook_or_provisional"
    require_binary_agreement: bool = False
    duplicate_policy: DuplicatePolicy = "preserve"
    include_prior_analysis: bool = True
    include_rag: bool = True
    include_periodic_context: bool = False


def dna_statement_coding_config(
    project_config: dict[str, Any] | None,
) -> DNAStatementCodingConfig:
    root = project_config or {}
    analysis = root.get("analysis") if isinstance(root.get("analysis"), dict) else {}
    raw = (
        analysis.get("dna_statement_coding")
        if isinstance(analysis.get("dna_statement_coding"), dict)
        else None
    )
    if raw is None and isinstance(root.get("dna_statement_coding"), dict):
        raw = root["dna_statement_coding"]
    return DNAStatementCodingConfig.model_validate(raw or {})


def dna_statement_coding_enabled(project_config: dict[str, Any] | None) -> bool:
    return dna_statement_coding_config(project_config).enabled


def _memory_text(entries: list[CodebookEntry]) -> str:
    rows: list[str] = []
    for entry in entries:
        aliases = ", ".join(entry.aliases)
        rows.append(f"- {entry.kind}: {entry.label}" + (f" (aliases: {aliases})" if aliases else ""))
    return "\n".join(rows)


def _filtered_previous_analysis(record: CanonicalRecord) -> str:
    selected: dict[str, Any] = {}
    for name, value in record.intermediate.stage_outputs.items():
        folded = name.casefold()
        if name in {
            "preprocess",
            "preprocess_contract",
            "summary_preanalysis",
            "multimodal_synthesis",
            "castells_context",
            "discourse_analysis",
        } or "laclau" in folded:
            selected[name] = value
    return json.dumps(
        {
            "frame_analysis": record.intermediate.frame_analysis,
            "stage_outputs": selected,
            "note": (
                "These are PRIOR_ANALYSIS proposals, not SOURCE_EVIDENCE. "
                "Use them only for disambiguation and candidate normalization."
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        indent=2,
    )


def _build_envelope(
    record: CanonicalRecord,
    context: "PipelineContext",
    config: DNAStatementCodingConfig,
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
        prompt_version=f"dna-statement-coding:{config.prompt_version}",
    )
    envelope.previous_analysis.text = (
        _filtered_previous_analysis(record) if config.include_prior_analysis else ""
    )
    return envelope


def _slug(value: str) -> str:
    value = re.sub(r"[^\w]+", "-", value.casefold(), flags=re.UNICODE).strip("-")
    return value[:80] or "unknown"


def _stable_id(prefix: str, label: str) -> str:
    digest = hashlib.sha256(label.strip().casefold().encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{_slug(label)}:{digest}"


def _record_id(record: CanonicalRecord) -> str:
    if record.source_native_ids:
        key = sorted(record.source_native_ids)[0]
        return f"{key}:{record.source_native_ids[key]}"
    return record.source_url


def _validated_span(text: str, candidate: DNAStatementCandidate) -> EvidenceSpan:
    quote = candidate.evidence_text
    if candidate.start is not None and candidate.stop is not None:
        if 0 <= candidate.start < candidate.stop <= len(text):
            if text[candidate.start : candidate.stop] == quote:
                return EvidenceSpan(
                    quote=quote,
                    start_char=candidate.start,
                    end_char=candidate.stop,
                    exact=True,
                )
    start = text.find(quote) if quote else -1
    if start >= 0:
        return EvidenceSpan(
            quote=quote,
            start_char=start,
            end_char=start + len(quote),
            exact=True,
        )
    return EvidenceSpan(quote=quote, exact=False)


def _agreement(candidate: DNAStatementCandidate) -> tuple[Stance, bool]:
    if candidate.agreement_status != "coded" or candidate.agreement is None:
        return Stance.UNKNOWN, True
    return (Stance.SUPPORT if candidate.agreement else Stance.OPPOSE), False


def _candidate_to_statement(
    record: CanonicalRecord,
    candidate: DNAStatementCandidate,
    *,
    index: int,
    config: DNAStatementCodingConfig,
    model: str,
    model_provider: str | None,
    codebook_version: str | None,
    prompt_meta: dict[str, Any],
) -> DiscourseStatement:
    person_label = candidate.person.label.strip() if candidate.person and candidate.person.label else ""
    org_label = (
        candidate.organization.label.strip()
        if candidate.organization and candidate.organization.label
        else ""
    )
    actor_label = person_label or org_label
    actor_id = (
        candidate.person.id
        if person_label and candidate.person and candidate.person.id
        else candidate.organization.id
        if org_label and candidate.organization and candidate.organization.id
        else _stable_id("actor", actor_label)
    )
    concept_id = candidate.concept.id or _stable_id("concept", candidate.concept.label)
    stance, abstained = _agreement(candidate)
    span = _validated_span(record.content.text, candidate)
    validation = ValidationStatus.PROVISIONAL if span.exact else ValidationStatus.NEEDS_REVIEW
    agreement_value = candidate.agreement if candidate.agreement_status == "coded" else None
    duplicate_key = "|".join(
        [
            _record_id(record),
            actor_id,
            concept_id,
            "true" if agreement_value is True else "false" if agreement_value is False else "null",
        ]
    )
    return DiscourseStatement(
        statement_id=f"dna:{hashlib.sha256((duplicate_key + ':' + str(index)).encode()).hexdigest()[:20]}",
        source_url=record.source_url,
        source_record_id=_record_id(record),
        actor_id=actor_id,
        actor_name=actor_label,
        concept_id=concept_id,
        concept_label=candidate.concept.label,
        original_concept_wording=candidate.concept.original_text,
        proposition=candidate.concept.label,
        concept_type="issue_position",
        stance=stance,
        timestamp=record.source.created_at,
        evidence=span,
        platform=record.source.platform or None,
        coder_type="llm",
        coder_id_or_model=model,
        model_provider=model_provider,
        model_version=model,
        confidence=candidate.confidence,
        codebook_version=codebook_version,
        validation_status=validation,
        abstained=abstained,
        metadata={
            "dna_statement_type": "DNA Statement",
            "person": candidate.person.model_dump(mode="json") if candidate.person else None,
            "organization": (
                candidate.organization.model_dump(mode="json") if candidate.organization else None
            ),
            "agreement": agreement_value,
            "agreement_status": candidate.agreement_status,
            "uncertainty_reason": candidate.uncertainty_reason,
            "concept_provisional": candidate.concept.provisional,
            "concept_mapping_confidence": candidate.concept.mapping_confidence,
            "duplicate_key": duplicate_key,
            "duplicate_policy": config.duplicate_policy,
            "notes": candidate.notes,
        },
        provenance={
            "analysis_method": "discourse_network_analysis",
            "prompt_version": config.prompt_version,
            **prompt_meta,
        },
    )


def _append_stage(record: CanonicalRecord, payload: dict[str, Any]) -> None:
    existing = record.intermediate.stage_outputs.get("dna_statement_coding")
    history = existing if isinstance(existing, list) else ([] if existing is None else [existing])
    history.append(payload)
    record.intermediate.stage_outputs["dna_statement_coding"] = history


def run_optional_dna_statement_coding(
    record: CanonicalRecord,
    *,
    provider,
    context: "PipelineContext",
    codebook_entries: list[CodebookEntry] | None = None,
    model: str = "auto",
    allow_cloud_fallback: bool | None = None,
) -> list[DiscourseStatement] | None:
    """Run DNA coding only when enabled and persist provisional canonical statements."""
    config = dna_statement_coding_config(context.project_config)
    if not config.enabled:
        return None

    system_resource = load_prompt("dna.statement_coding_system", version=config.prompt_version)
    task_resource = load_prompt("dna.statement_coding", version=config.prompt_version)
    rendered_task = task_resource.render(
        concept_mode=config.concept_mode,
        require_binary_agreement=str(config.require_binary_agreement).lower(),
        duplicate_policy=config.duplicate_policy,
    )
    envelope = _build_envelope(
        record,
        context,
        config,
        codebook_entries or [],
        rendered_task.text,
    )
    selected_model = config.model or model
    batch, response = chat_structured(
        provider,
        DNAStatementBatch,
        model=selected_model,
        system_prompt=system_resource.text,
        user_prompt=envelope.render(),
        allow_cloud_fallback=allow_cloud_fallback,
    )
    prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
    actual_model = response.provenance.actual_model or selected_model
    statements = [
        _candidate_to_statement(
            record,
            candidate,
            index=index,
            config=config,
            model=actual_model,
            model_provider=response.provenance.actual_mode,
            codebook_version=context.codebook_revision or None,
            prompt_meta=prompt_meta,
        )
        for index, candidate in enumerate(batch.statements, start=1)
    ]

    if config.require_binary_agreement:
        statements = [statement for statement in statements if not statement.abstained]

    run_meta = {
        **response.provenance.to_dict(),
        "prompt_version": config.prompt_version,
        "stage": "dna_statement_coding",
        "schema_version": batch.schema_version,
        "config_revision": context.config_revision,
        "codebook_revision": context.codebook_revision,
        "context_revision": context.context_revision,
        "project_config_revision": context.project_config_revision,
        **prompt_meta,
    }
    proposal = {
        "schema_version": batch.schema_version,
        "statements": [statement.model_dump(mode="json") for statement in statements],
        "abstentions": batch.abstentions,
    }
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": batch.schema_version,
        "prompt_version": config.prompt_version,
        **prompt_meta,
        "context_provenance": envelope.provenance_snapshot(),
        "configuration": config.model_dump(mode="json"),
        "proposal": proposal,
        "model_run": run_meta,
    }
    _append_stage(record, payload)
    record.analysis.plugin_results["dna_statement_coding"] = payload
    record.analysis.model_runs.append(run_meta)
    return statements
