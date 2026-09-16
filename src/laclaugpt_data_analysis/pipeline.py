"""Canonical provider-neutral LLM-assisted analysis orchestration."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .canonical import (
    CanonicalRecord,
    DiscourseObject,
    Entity,
    Evidence,
    Relation,
    RelationChain,
)
from .codebooks import CodebookEntry
from .llm.structured_output import chat_structured
from .memory.retrieval import context_block
from .models import ClassificationResult, Topic
from .prompt_library import load_prompt, prompt_provenance
from .research_record import ensure_research_layers


class EvidenceLinkedCandidate(BaseModel):
    label: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    uncertainty: str = ""


class RelationProposal(BaseModel):
    relation_type: str
    source: str
    target: str
    evidence: list[str] = Field(default_factory=list)


class ChainProposal(BaseModel):
    chain_type: Literal["equivalence", "difference"]
    members: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class AnalysisProposal(BaseModel):
    """Backend-neutral output surface retaining useful legacy analytical vocabulary."""

    summary: str = ""
    entities: list[str] = Field(default_factory=list)
    classifications: dict[str, str] = Field(default_factory=dict)
    topics: list[EvidenceLinkedCandidate] = Field(default_factory=list)
    themes: list[EvidenceLinkedCandidate] = Field(default_factory=list)
    sentiments: list[EvidenceLinkedCandidate] = Field(default_factory=list)
    stances: list[EvidenceLinkedCandidate] = Field(default_factory=list)
    formations: list[str] = Field(default_factory=list)
    signifiers: list[str] = Field(default_factory=list)
    nodal_points: list[str] = Field(default_factory=list)
    floating_signifiers: list[EvidenceLinkedCandidate] = Field(default_factory=list)
    empty_signifier_candidates: list[EvidenceLinkedCandidate] = Field(default_factory=list)
    discourses: list[str] = Field(default_factory=list)
    imaginaries: list[str] = Field(default_factory=list)
    equivalence_chains: list[ChainProposal] = Field(default_factory=list)
    difference_chains: list[ChainProposal] = Field(default_factory=list)
    antagonisms: list[RelationProposal] = Field(default_factory=list)
    actor_entity_relations: list[RelationProposal] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    abstentions: list[str] = Field(default_factory=list)


def _append_stage_output(record: CanonicalRecord, name: str, output: dict[str, Any]) -> None:
    existing = record.intermediate.stage_outputs.get(name)
    if not isinstance(existing, list):
        existing = [] if existing is None else [existing]
    existing.append(output)
    record.intermediate.stage_outputs[name] = existing


def _evidence_ids(record: CanonicalRecord, quotes: list[str], prefix: str) -> list[str]:
    ids: list[str] = []
    for quote in quotes:
        text = quote.strip()
        if not text:
            continue
        evidence_id = f"{prefix}:evidence:{len(record.evidence) + 1}"
        record.evidence.append(
            Evidence(
                evidence_id=evidence_id,
                kind="llm_proposed_source_evidence",
                source_url=record.source_url,
                quote=text,
                metadata={"review_status": "PROVISIONAL"},
            )
        )
        ids.append(evidence_id)
    return ids


def _candidate_objects(
    record: CanonicalRecord,
    values: list[EvidenceLinkedCandidate],
    kind: str,
) -> list[DiscourseObject]:
    corpus_required = kind in {"floating_signifier", "empty_signifier", "formation"}
    return [
        DiscourseObject(
            object_id=f"{kind}:{index}",
            label=item.label,
            kind=kind,
            evidence_ids=_evidence_ids(record, item.evidence, f"{kind}:{index}"),
            confidence=item.confidence,
            uncertainty=item.uncertainty or None,
            review_status="PROVISIONAL",
            metadata={"corpus_validation_required": corpus_required},
        )
        for index, item in enumerate(values, start=1)
    ]


def _relations(
    record: CanonicalRecord,
    values: list[RelationProposal],
    prefix: str,
) -> list[Relation]:
    return [
        Relation(
            relation_id=f"{prefix}:{index}",
            relation_type=item.relation_type,
            source_ref=item.source,
            target_ref=item.target,
            evidence_ids=_evidence_ids(record, item.evidence, f"{prefix}:{index}"),
            review_status="PROVISIONAL",
        )
        for index, item in enumerate(values, start=1)
    ]


def _chains(
    record: CanonicalRecord,
    values: list[ChainProposal],
    chain_type: Literal["equivalence", "difference"],
) -> list[RelationChain]:
    return [
        RelationChain(
            chain_id=f"{chain_type}_chain:{index}",
            chain_type=chain_type,
            member_refs=item.members,
            evidence_ids=_evidence_ids(record, item.evidence, f"{chain_type}_chain:{index}"),
            review_status="PROVISIONAL",
        )
        for index, item in enumerate(values, start=1)
        if item.chain_type == chain_type and len(item.members) >= 2
    ]


def analyze_record(
    record: CanonicalRecord,
    *,
    provider,
    codebook_entries: list[CodebookEntry] | None = None,
    model: str = "auto",
    prompt_version: str = "analysis-v2-parity",
    allow_cloud_fallback: bool | None = None,
) -> CanonicalRecord:
    """Enrich one canonical record without changing identity or deleting stage results."""
    entries = codebook_entries or []
    retrieved = context_block(record.content.text, entries) if entries else ""
    system_resource = load_prompt("laclau.system", version="v1")
    task_resource = load_prompt("laclau.document_analysis", version="v1")
    rendered_task = task_resource.render(
        source_url=record.source_url,
        source_text=record.content.text,
        codebook_context=retrieved or "(none available)",
    )
    proposal, response = chat_structured(
        provider,
        AnalysisProposal,
        model=model,
        system_prompt=system_resource.text,
        user_prompt=rendered_task.text,
        allow_cloud_fallback=allow_cloud_fallback,
    )

    now = datetime.now(UTC)
    record.analysis.status = "analyzed"
    record.analysis.started_at = record.analysis.started_at or now
    record.analysis.completed_at = now
    record.analysis.summary = proposal.summary or None
    record.analysis.entities = [
        Entity(entity_id=f"entity:{index}", label=label, review_status="PROVISIONAL")
        for index, label in enumerate(proposal.entities, start=1)
    ]
    record.analysis.classifications = [
        ClassificationResult(
            label=label,
            task=task,
            model=response.provenance.actual_model,
            backend=(
                "ollama"
                if response.provenance.actual_mode in {"local", "cloud", "external"}
                else response.provenance.actual_mode
            ),
            source_url=record.source_url,
        )
        for task, label in sorted(proposal.classifications.items())
    ]
    record.analysis.topics = [
        Topic(
            topic_id=f"topic:{index}",
            canonical_label=item.label,
            metadata={
                "evidence_ids": _evidence_ids(record, item.evidence, f"topic:{index}"),
                "confidence": item.confidence,
                "uncertainty": item.uncertainty,
                "review_status": "PROVISIONAL",
            },
        )
        for index, item in enumerate(proposal.topics, start=1)
    ]
    record.analysis.themes = _candidate_objects(record, proposal.themes, "theme")
    record.analysis.sentiments = _candidate_objects(record, proposal.sentiments, "sentiment")
    record.analysis.stances = _candidate_objects(record, proposal.stances, "stance")
    record.analysis.floating_signifiers = _candidate_objects(
        record, proposal.floating_signifiers, "floating_signifier"
    )
    record.analysis.empty_signifier_candidates = _candidate_objects(
        record, proposal.empty_signifier_candidates, "empty_signifier"
    )
    record.analysis.signifiers = [
        DiscourseObject(
            object_id=f"signifiers:{index}",
            label=label,
            kind="signifier",
            review_status="PROVISIONAL",
        )
        for index, label in enumerate(proposal.signifiers, start=1)
    ]
    record.analysis.signifiers.extend(record.analysis.floating_signifiers)
    record.analysis.signifiers.extend(record.analysis.empty_signifier_candidates)
    for field in ("formations", "nodal_points", "discourses", "imaginaries"):
        values = getattr(proposal, field)
        setattr(
            record.analysis,
            field,
            [
                DiscourseObject(
                    object_id=f"{field}:{index}",
                    label=label,
                    kind=field.rstrip("s"),
                    review_status="PROVISIONAL",
                    metadata={"corpus_validation_required": field == "formations"},
                )
                for index, label in enumerate(values, start=1)
            ],
        )
    record.analysis.equivalence_chains = _chains(record, proposal.equivalence_chains, "equivalence")
    record.analysis.difference_chains = _chains(record, proposal.difference_chains, "difference")
    record.analysis.antagonisms = _relations(record, proposal.antagonisms, "antagonism")
    record.analysis.actor_entity_relations = _relations(
        record, proposal.actor_entity_relations, "actor_entity_relation"
    )
    record.analysis.relations = [
        *record.analysis.antagonisms,
        *record.analysis.actor_entity_relations,
    ]
    record.analysis.uncertainty = proposal.uncertainty
    record.analysis.abstentions = proposal.abstentions
    record.analysis.codebook_refs = sorted({entry.label for entry in entries})
    prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
    model_run = {
        **response.provenance.to_dict(),
        "prompt_version": prompt_version,
        **prompt_meta,
    }
    record.analysis.model_runs.append(model_run)
    provenance = record.append_analysis_provenance(
        method="llm-assisted-analysis",
        model=response.provenance.actual_model,
        metadata={
            "provider": (
                "ollama"
                if response.provenance.actual_mode in {"local", "cloud", "external"}
                else response.provenance.actual_mode
            ),
            "prompt_version": prompt_version,
            "endpoint": response.provenance.endpoint,
            "fallback_used": response.provenance.fallback_used,
            **prompt_meta,
        },
    )
    for item in record.analysis.entities:
        item.provenance_id = provenance.provenance_id
    for collection in (
        record.analysis.themes,
        record.analysis.sentiments,
        record.analysis.stances,
        record.analysis.floating_signifiers,
        record.analysis.empty_signifier_candidates,
        record.analysis.formations,
        record.analysis.nodal_points,
        record.analysis.discourses,
        record.analysis.imaginaries,
    ):
        for item in collection:
            item.provenance_id = provenance.provenance_id
    for relation in (*record.analysis.antagonisms, *record.analysis.actor_entity_relations):
        relation.provenance_id = provenance.provenance_id
    for chain in (*record.analysis.equivalence_chains, *record.analysis.difference_chains):
        chain.provenance_id = provenance.provenance_id

    _append_stage_output(
        record,
        "llm_analysis",
        {
            "created_at": now.isoformat(),
            "prompt_version": prompt_version,
            **prompt_meta,
            "model_run": model_run,
            "proposal": proposal.model_dump(mode="json"),
            "provenance_id": provenance.provenance_id,
        },
    )
    return ensure_research_layers(record)
