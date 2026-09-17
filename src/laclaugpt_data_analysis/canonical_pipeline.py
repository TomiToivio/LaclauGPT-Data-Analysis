"""Canonical staged LaclauGPT analysis orchestration.

The orchestration preserves the legacy multimodal/human-readable ladder while using
current evidence-first discourse-analysis contracts. Expensive preprocessing remains
pluggable so the same pipeline can run on a laptop, CSC Roihu, or a Linux server.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, field_validator

from .canonical import (
    CanonicalRecord,
    DiscourseObject,
    Entity,
    Evidence,
    Relation,
    RelationChain,
)
from .models import Topic
from .codebooks import CodebookEntry
from .context_envelope import PromptEnvelope, build_prompt_envelope
from .critical_ai import run_optional_critical_ai
from .llm.structured_output import chat_structured
from .prompt_library import load_prompt, prompt_provenance
from .research_record import ensure_research_layers


class PipelineContext(BaseModel):
    project_context: str = ""
    source_context: str = ""
    situational_context: str = ""
    memory_context: str = ""
    rag_context: str = ""
    provenance: dict[str, list[str]] = Field(default_factory=dict)
    config_revision: str = ""
    codebook_revision: str = ""
    context_revision: str = ""
    project_config_revision: str = ""
    project_config: dict[str, Any] = Field(default_factory=dict)


class FrameProposal(BaseModel):
    """Historical frame schema retained for EP24/generic reproducibility."""

    description: str = ""
    framing: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    visible_text: list[str] = Field(default_factory=list)
    usernames: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    rhetorical_cues: list[str] = Field(default_factory=list)
    candidate_signifiers: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


class MultimodalFrameProposal(BaseModel):
    """Evidence-first semiotic frame description used by the AI26 pre-analysis path."""

    material_canvas_organisation: list[str] = Field(default_factory=list)
    scene_and_participants: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    visual_composition: list[str] = Field(default_factory=list)
    visible_text: list[str] = Field(default_factory=list)
    usernames: list[str] = Field(default_factory=list)
    symbols_and_interface_cues: list[str] = Field(default_factory=list)
    provenance_and_usage_cues: list[str] = Field(default_factory=list)
    semiotic_contribution: str = ""
    uncertainty: list[str] = Field(default_factory=list)


class _CoerceStringListFields:
    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def _single_value_to_list(cls, value: Any, info: Any) -> Any:
        name = getattr(info, "field_name", "")
        model_fields = getattr(cls, "model_fields", {})
        declared = model_fields.get(name)
        if declared is None:
            return value
        annotation = str(declared.annotation)
        is_string_list = "list[str]" in annotation.replace(" ", "") or (
            "list" in annotation and "str" in annotation
        )
        if not is_string_list:
            return value
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return value


class EventCandidate(_CoerceStringListFields, BaseModel):
    description: str = ""
    time: str = ""
    location: str = ""
    actors: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)


class SummaryProposal(_CoerceStringListFields, BaseModel):
    summary: str = ""
    narrative: str = ""
    domain_classification: str = ""
    difficult_language: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    sentiment_observations: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    demands: list[str] = Field(default_factory=list)
    grievances: list[str] = Field(default_factory=list)
    event_candidates: list[EventCandidate] = Field(default_factory=list)
    candidate_signifiers: list[str] = Field(default_factory=list)
    candidate_articulations: list[str] = Field(default_factory=list)
    candidate_collective_subjects: list[str] = Field(default_factory=list)
    candidate_frontiers: list[str] = Field(default_factory=list)
    ai_definition_claims: list[str] = Field(default_factory=list)
    ai_capability_claims: list[str] = Field(default_factory=list)
    desirable_futures: list[str] = Field(default_factory=list)
    feared_futures: list[str] = Field(default_factory=list)
    sociotechnical_imaginary_candidates: list[str] = Field(default_factory=list)
    ownership_governance_assumptions: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


class CastellsContextProposal(BaseModel):
    actors_organisations_institutions: list[str] = Field(default_factory=list)
    networks_relations: list[str] = Field(default_factory=list)
    flows: list[str] = Field(default_factory=list)
    nodes_hubs_channels: list[str] = Field(default_factory=list)
    space_of_places: list[str] = Field(default_factory=list)
    space_of_flows: list[str] = Field(default_factory=list)
    power_access_exclusion: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


class MultimodalSummaryProposal(_CoerceStringListFields, BaseModel):
    summary: str = ""
    narrative: str = ""
    semiotic_modes: list[str] = Field(default_factory=list)
    cross_modal_relations: list[str] = Field(default_factory=list)
    difficult_language: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    sentiment_observations: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    demands: list[str] = Field(default_factory=list)
    grievances: list[str] = Field(default_factory=list)
    event_candidates: list[EventCandidate] = Field(default_factory=list)
    castells_context: CastellsContextProposal = Field(default_factory=CastellsContextProposal)
    later_analysis_cues: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


class DiscursiveElement(BaseModel):
    label: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    uncertainty: str = ""


class DiscursiveRelation(BaseModel):
    relation_type: str
    source: str
    target: str
    evidence: list[str] = Field(default_factory=list)


class DiscourseProposal(BaseModel):
    demands: list[DiscursiveElement] = Field(default_factory=list)
    articulations: list[DiscursiveRelation] = Field(default_factory=list)
    equivalences: list[DiscursiveRelation] = Field(default_factory=list)
    differences: list[DiscursiveRelation] = Field(default_factory=list)
    antagonisms: list[DiscursiveRelation] = Field(default_factory=list)
    collective_subjects: list[DiscursiveElement] = Field(default_factory=list)
    frontiers: list[DiscursiveElement] = Field(default_factory=list)
    affects: list[DiscursiveElement] = Field(default_factory=list)
    nodal_point_candidates: list[DiscursiveElement] = Field(default_factory=list)
    floating_signifier_candidates: list[DiscursiveElement] = Field(default_factory=list)
    empty_signifier_candidates: list[DiscursiveElement] = Field(default_factory=list)
    formation_candidates: list[DiscursiveElement] = Field(default_factory=list)
    imaginary_candidates: list[DiscursiveElement] = Field(default_factory=list)
    populist: bool = False
    non_populist_reason: str = ""
    formula_of_populism: dict[str, Any] = Field(default_factory=dict)
    counter_evidence: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    abstentions: list[str] = Field(default_factory=list)


class GraphSink(Protocol):
    def write_graph(self, source_url: str, graph: dict[str, Any]) -> None: ...


class VectorSink(Protocol):
    def upsert(self, source_url: str, text: str, metadata: dict[str, Any]) -> None: ...


Preprocessor = Callable[[CanonicalRecord], dict[str, Any] | None]
SummaryResult = SummaryProposal | MultimodalSummaryProposal

_AI26_CAPABILITIES = {
    "laclau": "discourse",
    "palonen": "discourse",
    "sociotechnical_imaginaries": "discourse",
    "sentiment": "summary_projection",
    "topics": "summary_projection",
    "entities": "summary_projection",
    "context_memory": "context",
    "temporal": "summary",
    "multimodal": "frame_summary",
    "sna": None,
    "ant": None,
    "valueflows": None,
}


def _analysis_flags(context: PipelineContext) -> dict[str, Any]:
    analysis = context.project_config.get("analysis") if context.project_config else None
    return dict(analysis) if isinstance(analysis, dict) else {}


def _enabled(context: PipelineContext, key: str, *, default: bool = True) -> bool:
    value = _analysis_flags(context).get(key, default)
    if isinstance(value, dict):
        return bool(value.get("enabled", default))
    return bool(value)


def _effective_stage_set(context: PipelineContext) -> list[str]:
    stages: list[str] = []
    for key, implementation in _AI26_CAPABILITIES.items():
        if _enabled(context, key, default=False) and implementation:
            stages.append(key)
    for key in ("dna_statement_coding", "critical_ai"):
        if _enabled(context, key, default=False):
            stages.append(key)
    return sorted(stages)


def _validate_project_analysis_config(context: PipelineContext) -> None:
    flags = _analysis_flags(context)
    if not flags:
        return
    unknown = sorted(set(flags) - set(_AI26_CAPABILITIES) - {"dna_statement_coding", "critical_ai"})
    if unknown:
        raise ValueError(f"unknown analysis capability flag(s): {', '.join(unknown)}")
    unavailable = sorted(
        key for key, implementation in _AI26_CAPABILITIES.items()
        if flags.get(key) is True and implementation is None
    )
    if unavailable:
        raise ValueError(
            "project enables unavailable analysis capability/capabilities: " + ", ".join(unavailable)
        )


def _append_stage(record: CanonicalRecord, name: str, payload: dict[str, Any]) -> None:
    existing = record.intermediate.stage_outputs.get(name)
    history = existing if isinstance(existing, list) else ([] if existing is None else [existing])
    history.append(payload)
    record.intermediate.stage_outputs[name] = history


def _memory_text(entries: list[CodebookEntry]) -> str:
    lines = []
    for entry in entries:
        aliases = ", ".join(entry.aliases)
        lines.append(f"- {entry.kind}: {entry.label}" + (f" (aliases: {aliases})" if aliases else ""))
    return "\n".join(lines)


def _envelope(record: CanonicalRecord, context: PipelineContext, *, task: str, codebook_entries: list[CodebookEntry], prompt_version: str) -> PromptEnvelope:
    memory = "\n".join(part for part in (context.memory_context, _memory_text(codebook_entries)) if part)
    return build_prompt_envelope(record, task=task, project_context=context.project_context, source_context=context.source_context, situational_context=context.situational_context, memory_context=memory, rag_context=context.rag_context, context_provenance=context.provenance, prompt_version=prompt_version)


def _project_config_sha256(context: PipelineContext) -> str:
    if not context.project_config:
        return ""
    payload = json.dumps(context.project_config, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _model_run_metadata(context: PipelineContext, response, prompt_meta: dict[str, Any], *, prompt_version: str, stage: str) -> dict[str, Any]:
    return {**response.provenance.to_dict(), "prompt_version": prompt_version, "stage": stage, "config_revision": context.config_revision, "codebook_revision": context.codebook_revision, "context_revision": context.context_revision, "project_config_revision": context.project_config_revision, "project_config_sha256": _project_config_sha256(context), "effective_analysis_stages": _effective_stage_set(context), **prompt_meta}


def prompt_ids_for_stage(project_profile: str, stage: str) -> tuple[str, str]:
    profile = project_profile.casefold()
    if stage == "frame":
        return ("multimodal.system", "multimodal.frame_analysis") if profile == "ai26" else ("laclau.system", "laclau.frame_analysis")
    if stage == "summary":
        return ("multimodal.system", "multimodal.summary_analysis") if profile == "ai26" else ("laclau.system", "laclau.summary_analysis")
    if stage == "discourse":
        return "laclau.system", "laclau.discourse_analysis"
    raise ValueError(f"unsupported canonical pipeline stage: {stage}")


def _summary_markdown(proposal: MultimodalSummaryProposal) -> str:
    parts = ["# Multimodal item synthesis", proposal.narrative or proposal.summary]
    if proposal.cross_modal_relations:
        parts.extend(("## Cross-modal relations", "\n".join(f"- {x}" for x in proposal.cross_modal_relations)))
    return "\n\n".join(part for part in parts if part).strip()


def preprocess_record(record: CanonicalRecord, *, preprocessor: Preprocessor | None = None) -> CanonicalRecord:
    payload = preprocessor(record) if preprocessor else None
    if payload:
        for key in ("asr", "ocr", "frames", "translations"):
            values = payload.get(key)
            if values:
                getattr(record.intermediate, key).extend(values)
        if payload.get("legacy"):
            record.legacy.update(payload["legacy"])
        if payload.get("stage_output"):
            _append_stage(record, "preprocess", payload["stage_output"])
    _append_stage(record, "preprocess_contract", {"created_at": datetime.now(UTC).isoformat(), "source_preserved": record.raw_capture.preserved or bool(record.source.raw_metadata), "legacy_fields_preserved": sorted(record.legacy)})
    return record


def analyze_frames(record: CanonicalRecord, *, provider, context: PipelineContext, codebook_entries: list[CodebookEntry], model: str, prompt_version: str, project_profile: str, allow_cloud_fallback: bool | None) -> CanonicalRecord:
    if not record.content.frames or (project_profile.casefold() == "ai26" and not _enabled(context, "multimodal")):
        return record
    system_id, task_id = prompt_ids_for_stage(project_profile, "frame")
    system_resource = load_prompt(system_id, version="v1")
    task_resource = load_prompt(task_id, version="v1")
    ai26_multimodal = project_profile.casefold() == "ai26"
    for frame in record.content.frames:
        rendered_task = task_resource.render(frame_id=frame.id, timestamp_seconds=frame.timestamp_seconds, project_note="AI26 relevance guide only" if ai26_multimodal else "Generic descriptive frame analysis.")
        envelope = _envelope(record, context, task=rendered_task.text, codebook_entries=codebook_entries, prompt_version=prompt_version)
        proposal_model = MultimodalFrameProposal if ai26_multimodal else FrameProposal
        proposal, response = chat_structured(provider, proposal_model, model=model, system_prompt=system_resource.text, user_prompt=envelope.render(), allow_cloud_fallback=allow_cloud_fallback)
        prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
        run_meta = _model_run_metadata(context, response, prompt_meta, prompt_version=prompt_version, stage="multimodal_frame" if ai26_multimodal else "frame")
        record.intermediate.frame_analysis.append({"frame_id": frame.id, "timestamp_seconds": frame.timestamp_seconds, "analysis": proposal.model_dump(mode="json"), "prompt_version": prompt_version, **prompt_meta, "context_provenance": envelope.provenance_snapshot(), "model_run": run_meta})
        record.analysis.model_runs.append(run_meta)
    return record


def summarize_record(record: CanonicalRecord, *, provider, context: PipelineContext, codebook_entries: list[CodebookEntry], model: str, prompt_version: str, project_profile: str, allow_cloud_fallback: bool | None) -> SummaryResult:
    ai26_multimodal = project_profile.casefold() == "ai26"
    system_id, task_id = prompt_ids_for_stage(project_profile, "summary")
    system_resource = load_prompt(system_id, version="v1")
    task_resource = load_prompt(task_id, version="v1")
    rendered_task = task_resource.render(project_note="AI26 multimodal/light sociology summary." if ai26_multimodal else "(none)")
    envelope = _envelope(record, context, task=rendered_task.text, codebook_entries=codebook_entries, prompt_version=prompt_version)
    proposal_model = MultimodalSummaryProposal if ai26_multimodal else SummaryProposal
    proposal, response = chat_structured(provider, proposal_model, model=model, system_prompt=system_resource.text, user_prompt=envelope.render(), allow_cloud_fallback=allow_cloud_fallback)
    prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
    run_meta = _model_run_metadata(context, response, prompt_meta, prompt_version=prompt_version, stage="multimodal_summary" if ai26_multimodal else "summary")
    now = datetime.now(UTC).isoformat()
    record.human_readable.summary = proposal.summary
    record.human_readable.generated_at = now
    record.human_readable.markdown = _summary_markdown(proposal) if isinstance(proposal, MultimodalSummaryProposal) else (proposal.narrative or proposal.summary)
    record.analysis.model_runs.append(run_meta)
    _append_stage(record, "multimodal_synthesis" if ai26_multimodal else "summary_preanalysis", {"created_at": now, "prompt_version": prompt_version, **prompt_meta, "context_provenance": envelope.provenance_snapshot(), "proposal": proposal.model_dump(mode="json"), "model_run": run_meta})
    return proposal


def discourse_analysis(record: CanonicalRecord, *, provider, context: PipelineContext, codebook_entries: list[CodebookEntry], model: str, prompt_version: str, project_profile: str, allow_cloud_fallback: bool | None) -> DiscourseProposal:
    system_id, task_id = prompt_ids_for_stage(project_profile, "discourse")
    system_resource = load_prompt(system_id, version="v1")
    task_resource = load_prompt(task_id, version="v1")
    rendered_task = task_resource.render(project_note="AI26 discourse analysis." if project_profile.casefold() == "ai26" else "(none)")
    envelope = _envelope(record, context, task=rendered_task.text, codebook_entries=codebook_entries, prompt_version=prompt_version)
    proposal, response = chat_structured(provider, DiscourseProposal, model=model, system_prompt=system_resource.text, user_prompt=envelope.render(), allow_cloud_fallback=allow_cloud_fallback)
    prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
    run_meta = _model_run_metadata(context, response, prompt_meta, prompt_version=prompt_version, stage="discourse")
    _append_stage(record, "discourse_analysis", {"created_at": datetime.now(UTC).isoformat(), "prompt_version": prompt_version, **prompt_meta, "context_provenance": envelope.provenance_snapshot(), "proposal": proposal.model_dump(mode="json"), "model_run": run_meta})
    record.analysis.model_runs.append(run_meta)
    return proposal


def _evidence_ids(record: CanonicalRecord, quotes: list[str], prefix: str) -> list[str]:
    ids: list[str] = []
    for quote in quotes:
        text = quote.strip()
        if text:
            evidence_id = f"{prefix}:evidence:{len(record.evidence) + 1}"
            record.evidence.append(Evidence(evidence_id=evidence_id, kind="llm_proposed_source_evidence", source_url=record.source_url, quote=text, metadata={"review_status": "PROVISIONAL"}))
            ids.append(evidence_id)
    return ids


def _objects(record: CanonicalRecord, items: list[DiscursiveElement], kind: str) -> list[DiscourseObject]:
    corpus_required = kind in {"floating_signifier", "empty_signifier", "formation"}
    return [DiscourseObject(object_id=f"{kind}:{index}", label=item.label, kind=kind, evidence_ids=_evidence_ids(record, item.evidence, f"{kind}:{index}"), confidence=item.confidence, uncertainty=item.uncertainty, review_status="PROVISIONAL", metadata={"corpus_validation_required": corpus_required}) for index, item in enumerate(items, start=1)]


def _relation_chains(record: CanonicalRecord, relations: list[DiscursiveRelation], chain_type: Literal["equivalence", "difference"]) -> list[RelationChain]:
    return [RelationChain(chain_id=f"{chain_type}_chain:{index}", chain_type=chain_type, member_refs=[item.source, item.target], evidence_ids=_evidence_ids(record, item.evidence, f"{chain_type}_chain:{index}"), review_status="PROVISIONAL") for index, item in enumerate(relations, start=1) if item.source and item.target and item.source != item.target]


def _project_summary_capabilities(record: CanonicalRecord, summary: SummaryResult, context: PipelineContext) -> None:
    if _enabled(context, "entities"):
        record.analysis.entities = [Entity(entity_id=f"summary-entity:{i}", label=label, review_status="PROVISIONAL") for i, label in enumerate(summary.entities, start=1)]
    if _enabled(context, "topics"):
        record.analysis.topics = [Topic(topic_id=f"summary-topic:{i}", canonical_label=label, metadata={"source_stage": "summary", "review_status": "PROVISIONAL"}) for i, label in enumerate(summary.topics, start=1)]
    if _enabled(context, "sentiment"):
        record.analysis.sentiments = [DiscourseObject(object_id=f"summary-sentiment:{i}", label=label, kind="sentiment", review_status="PROVISIONAL", metadata={"source_stage": "summary"}) for i, label in enumerate(summary.sentiment_observations, start=1)]


def postprocess_record(record: CanonicalRecord, summary: SummaryResult, discourse: DiscourseProposal, context: PipelineContext | None = None) -> CanonicalRecord:
    ctx = context or PipelineContext()
    record.analysis.status = "analyzed"
    record.analysis.summary = summary.summary or None
    _project_summary_capabilities(record, summary, ctx)
    record.analysis.floating_signifiers = _objects(record, discourse.floating_signifier_candidates, "floating_signifier")
    record.analysis.empty_signifier_candidates = _objects(record, discourse.empty_signifier_candidates, "empty_signifier")
    record.analysis.signifiers = list(record.analysis.floating_signifiers) + list(record.analysis.empty_signifier_candidates)
    record.analysis.nodal_points = _objects(record, discourse.nodal_point_candidates, "nodal_point")
    record.analysis.formations = _objects(record, discourse.formation_candidates, "formation")
    record.analysis.imaginaries = _objects(record, discourse.imaginary_candidates, "imaginary") if _enabled(ctx, "sociotechnical_imaginaries") else []
    record.analysis.us = _objects(record, discourse.collective_subjects, "collective_subject")
    record.analysis.frontier = _objects(record, discourse.frontiers, "frontier")
    record.analysis.affects = _objects(record, discourse.affects, "affect")
    record.analysis.formula_of_populism = {"populist": discourse.populist, "non_populist_reason": discourse.non_populist_reason, **discourse.formula_of_populism}
    record.analysis.uncertainty = list(dict.fromkeys(summary.uncertainty + discourse.uncertainty))
    record.analysis.abstentions = discourse.abstentions
    record.analysis.equivalence_chains = _relation_chains(record, discourse.equivalences, "equivalence")
    record.analysis.difference_chains = _relation_chains(record, discourse.differences, "difference")
    record.analysis.antagonisms = [Relation(relation_id=f"antagonism:{i}", relation_type=item.relation_type, source_ref=item.source, target_ref=item.target, evidence_ids=_evidence_ids(record, item.evidence, f"antagonism:{i}"), review_status="PROVISIONAL") for i, item in enumerate(discourse.antagonisms, start=1)]
    relations = discourse.articulations + discourse.equivalences + discourse.differences + discourse.antagonisms
    record.analysis.relations = [Relation(relation_id=f"relation:{i}", relation_type=item.relation_type, source_ref=item.source, target_ref=item.target, evidence_ids=_evidence_ids(record, item.evidence, f"relation:{i}"), review_status="PROVISIONAL") for i, item in enumerate(relations, start=1)]
    _append_stage(record, "effective_analysis_stages", {"stages": _effective_stage_set(ctx), "project_config_revision": ctx.project_config_revision, "project_config_sha256": _project_config_sha256(ctx)})
    record.analysis.completed_at = datetime.now(UTC)
    return ensure_research_layers(record)


def build_discourse_graph(record: CanonicalRecord) -> dict[str, Any]:
    nodes = [{"id": record.source_url, "type": "document", "label": record.content.title or record.source_url}]
    edges: list[dict[str, Any]] = []
    for obj in record.analysis.signifiers + record.analysis.formations + record.analysis.imaginaries + record.analysis.nodal_points:
        nodes.append({"id": obj.object_id, "type": obj.kind, "label": obj.label, "review_status": obj.review_status})
        edges.append({"source": record.source_url, "target": obj.object_id, "type": "CANDIDATE_IN"})
    return {"schema": "laclaugpt-discourse-graph-v1", "source_url": record.source_url, "nodes": nodes, "edges": edges}


def run_canonical_pipeline(record: CanonicalRecord, *, provider, context: PipelineContext | None = None, codebook_entries: list[CodebookEntry] | None = None, preprocessor: Preprocessor | None = None, graph_sink: GraphSink | None = None, vector_sink: VectorSink | None = None, model: str = "auto", project_profile: str = "generic", prompt_version: str = "canonical-pipeline-v1", allow_cloud_fallback: bool | None = None) -> CanonicalRecord:
    ctx = context or PipelineContext()
    if project_profile.casefold() == "ai26":
        _validate_project_analysis_config(ctx)
    entries = codebook_entries or []
    record.analysis.started_at = record.analysis.started_at or datetime.now(UTC)
    preprocess_record(record, preprocessor=preprocessor)
    analyze_frames(record, provider=provider, context=ctx, codebook_entries=entries, model=model, prompt_version=f"{prompt_version}:frame", project_profile=project_profile, allow_cloud_fallback=allow_cloud_fallback)
    summary = summarize_record(record, provider=provider, context=ctx, codebook_entries=entries, model=model, prompt_version=f"{prompt_version}:summary", project_profile=project_profile, allow_cloud_fallback=allow_cloud_fallback)
    discourse = discourse_analysis(record, provider=provider, context=ctx, codebook_entries=entries, model=model, prompt_version=f"{prompt_version}:discourse", project_profile=project_profile, allow_cloud_fallback=allow_cloud_fallback) if _enabled(ctx, "laclau") or project_profile.casefold() != "ai26" else DiscourseProposal()
    run_optional_critical_ai(record, provider=provider, context=ctx, codebook_entries=entries, model=model, allow_cloud_fallback=allow_cloud_fallback)
    postprocess_record(record, summary, discourse, ctx)
    graph = build_discourse_graph(record)
    _append_stage(record, "discourse_graph", graph)
    if graph_sink:
        graph_sink.write_graph(record.source_url, graph)
    if vector_sink:
        vector_sink.upsert(record.source_url, record.human_readable.markdown or record.content.text, {"source_url": record.source_url, "project_profile": project_profile})
    return record
