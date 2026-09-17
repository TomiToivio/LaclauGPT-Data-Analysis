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
from .codebooks import CodebookEntry
from .context_envelope import PromptEnvelope, build_prompt_envelope
from .critical_ai import run_optional_critical_ai
from .llm.structured_output import chat_structured
from .models import Topic
from .prompt_library import load_prompt, prompt_provenance
from .research_record import ensure_research_layers
from .stage_contract import resolve_stage_contract, stage_enabled


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
    """Accept a bare string where a list of strings is declared."""

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
    """Historical summary schema retained for EP24/generic reproducibility."""

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
    """Light, evidence-backed Network Society context; not formal SNA."""

    actors_organisations_institutions: list[str] = Field(default_factory=list)
    networks_relations: list[str] = Field(default_factory=list)
    flows: list[str] = Field(default_factory=list)
    nodes_hubs_channels: list[str] = Field(default_factory=list)
    space_of_places: list[str] = Field(default_factory=list)
    space_of_flows: list[str] = Field(default_factory=list)
    power_access_exclusion: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


class MultimodalSummaryProposal(_CoerceStringListFields, BaseModel):
    """AI26 item-level semiotic synthesis before discourse-theoretical analysis."""

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


_AI26_FRAME_NOTE = (
    "AI26 relevance guide only, not source evidence: when actually present, pay attention to "
    "AI/LLM interfaces and demos; labs, firms, researchers, investors and policy actors; "
    "data centres, compute, chips and energy infrastructure; robots/embodied AI; AI-generated "
    "media; benchmarks, charts and technical diagrams; regulation, safety, labour, automation "
    "and environmental material; protests, memes, online communities and movement imagery; "
    "and quoted news/media/platform material. Do not classify ideology at frame level."
)

_AI26_SUMMARY_NOTE = (
    "AI26 relevance guide only, not source evidence: keep attention available for AI/LLM "
    "interfaces, firms/labs/policy actors, compute/data-centre infrastructure, embodied AI, "
    "generated media, benchmarks/charts, regulation/safety/labour/environmental material, "
    "protests/memes/online communities and quoted media when they are actually evidenced. "
    "Keep ideological formations, populism, hegemony, DNA and Critical AI Studies for later stages."
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
        lines.append(
            f"- {entry.kind}: {entry.label}" + (f" (aliases: {aliases})" if aliases else "")
        )
    return "\n".join(lines)


def _envelope(record: CanonicalRecord, context: PipelineContext, *, task: str, codebook_entries: list[CodebookEntry], prompt_version: str) -> PromptEnvelope:
    memory = "\n".join(part for part in (context.memory_context, _memory_text(codebook_entries)) if part)
    return build_prompt_envelope(
        record,
        task=task,
        project_context=context.project_context,
        source_context=context.source_context,
        situational_context=context.situational_context,
        memory_context=memory,
        rag_context=context.rag_context,
        context_provenance=context.provenance,
        prompt_version=prompt_version,
    )


def _project_config_sha256(context: PipelineContext) -> str:
    if not context.project_config:
        return ""
    payload = json.dumps(context.project_config, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _model_run_metadata(context: PipelineContext, response, prompt_meta: dict[str, Any], *, prompt_version: str, stage: str) -> dict[str, Any]:
    return {
        **response.provenance.to_dict(),
        "prompt_version": prompt_version,
        "stage": stage,
        "config_revision": context.config_revision,
        "codebook_revision": context.codebook_revision,
        "context_revision": context.context_revision,
        "project_config_revision": context.project_config_revision,
        "project_config_sha256": _project_config_sha256(context),
        **prompt_meta,
    }


def prompt_ids_for_stage(project_profile: str, stage: str) -> tuple[str, str]:
    profile = project_profile.casefold()
    if stage == "frame":
        if profile == "ai26":
            return "multimodal.system", "multimodal.frame_analysis"
        return "laclau.system", "laclau.frame_analysis"
    if stage == "summary":
        if profile == "ai26":
            return "multimodal.system", "multimodal.summary_analysis"
        return "laclau.system", "laclau.summary_analysis"
    if stage == "discourse":
        return "laclau.system", "laclau.discourse_analysis"
    raise ValueError(f"unsupported canonical pipeline stage: {stage}")


def _summary_markdown(proposal: MultimodalSummaryProposal) -> str:
    parts = ["# Multimodal item synthesis", proposal.narrative or proposal.summary]
    if proposal.cross_modal_relations:
        parts.extend(("## Cross-modal relations", "\n".join(f"- {x}" for x in proposal.cross_modal_relations)))
    castells = proposal.castells_context
    castells_rows = {
        "Actors / organisations / institutions": castells.actors_organisations_institutions,
        "Networks / relations": castells.networks_relations,
        "Flows": castells.flows,
        "Nodes / hubs / channels": castells.nodes_hubs_channels,
        "Space of places": castells.space_of_places,
        "Space of flows": castells.space_of_flows,
        "Power / access / exclusion": castells.power_access_exclusion,
    }
    rendered_castells = [f"**{label}:** " + "; ".join(values) for label, values in castells_rows.items() if values]
    if rendered_castells:
        parts.extend(("## Light Castells sociological context", "\n\n".join(rendered_castells)))
    if proposal.later_analysis_cues:
        parts.extend(("## Later analysis cues", "\n".join(f"- {x}" for x in proposal.later_analysis_cues)))
    if proposal.uncertainty or castells.uncertainty:
        uncertainty = list(dict.fromkeys(proposal.uncertainty + castells.uncertainty))
        parts.extend(("## Uncertainty / evidence limits", "\n".join(f"- {x}" for x in uncertainty)))
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
    if not record.content.frames:
        return record
    system_id, task_id = prompt_ids_for_stage(project_profile, "frame")
    system_resource = load_prompt(system_id, version="v1")
    task_resource = load_prompt(task_id, version="v1")
    ai26_multimodal = project_profile.casefold() == "ai26"
    for frame in record.content.frames:
        if project_profile.casefold() == "ep24":
            profile_note = "EP24: preserve legacy election visual categories: framing, scene, activity, objects, subjects, flags/symbols, platform cues and visible text."
        elif ai26_multimodal:
            profile_note = _AI26_FRAME_NOTE
        else:
            profile_note = "Generic descriptive frame analysis; avoid unsupported identities or claims."
        rendered_task = task_resource.render(frame_id=frame.id, timestamp_seconds=frame.timestamp_seconds, project_note=profile_note)
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
    project_note = _AI26_SUMMARY_NOTE if ai26_multimodal else "(none)"
    system_id, task_id = prompt_ids_for_stage(project_profile, "summary")
    system_resource = load_prompt(system_id, version="v1")
    task_resource = load_prompt(task_id, version="v1")
    rendered_task = task_resource.render(project_note=project_note)
    envelope = _envelope(record, context, task=rendered_task.text, codebook_entries=codebook_entries, prompt_version=prompt_version)
    proposal_model = MultimodalSummaryProposal if ai26_multimodal else SummaryProposal
    proposal, response = chat_structured(provider, proposal_model, model=model, system_prompt=system_resource.text, user_prompt=envelope.render(), allow_cloud_fallback=allow_cloud_fallback)
    prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
    run_meta = _model_run_metadata(context, response, prompt_meta, prompt_version=prompt_version, stage="multimodal_summary" if ai26_multimodal else "summary")
    now = datetime.now(UTC).isoformat()
    record.human_readable.summary = proposal.summary
    record.human_readable.generated_at = now
    if isinstance(proposal, MultimodalSummaryProposal):
        record.human_readable.markdown = _summary_markdown(proposal)
        record.human_readable.sections.update({"multimodal_narrative": proposal.narrative, "semiotic_modes": "\n".join(proposal.semiotic_modes), "cross_modal_relations": "\n".join(proposal.cross_modal_relations), "topics": "\n".join(proposal.topics), "entities": "\n".join(proposal.entities), "sentiment": "\n".join(proposal.sentiment_observations), "claims": "\n".join(proposal.claims), "demands": "\n".join(proposal.demands), "grievances": "\n".join(proposal.grievances), "castells_context": json.dumps(proposal.castells_context.model_dump(mode="json"), ensure_ascii=False, sort_keys=True), "later_analysis_cues": "\n".join(proposal.later_analysis_cues)})
        synthesis_payload = {"created_at": now, "prompt_version": prompt_version, **prompt_meta, "context_provenance": envelope.provenance_snapshot(), "proposal": proposal.model_dump(mode="json"), "model_run": run_meta}
        _append_stage(record, "multimodal_synthesis", synthesis_payload)
        _append_stage(record, "castells_context", {"created_at": now, "prompt_version": prompt_version, **prompt_meta, "context_provenance": envelope.provenance_snapshot(), "proposal": proposal.castells_context.model_dump(mode="json"), "model_run": run_meta})
    else:
        record.human_readable.markdown = proposal.narrative or proposal.summary
        record.human_readable.sections.update({"narrative": proposal.narrative, "topics": "\n".join(proposal.topics), "entities": "\n".join(proposal.entities), "sentiment": "\n".join(proposal.sentiment_observations), "claims": "\n".join(proposal.claims), "demands": "\n".join(proposal.demands), "grievances": "\n".join(proposal.grievances), "candidate_signifiers": "\n".join(proposal.candidate_signifiers), "sociotechnical_imaginaries": "\n".join(proposal.sociotechnical_imaginary_candidates)})
        _append_stage(record, "summary_preanalysis", {"created_at": now, "prompt_version": prompt_version, **prompt_meta, "context_provenance": envelope.provenance_snapshot(), "proposal": proposal.model_dump(mode="json"), "model_run": run_meta})
    record.analysis.model_runs.append(run_meta)
    return proposal


def discourse_analysis(record: CanonicalRecord, *, provider, context: PipelineContext, codebook_entries: list[CodebookEntry], model: str, prompt_version: str, project_profile: str, allow_cloud_fallback: bool | None) -> DiscourseProposal:
    project_note = "(none)"
    if project_profile.casefold() == "ai26":
        project_note = "Also identify evidence-supported candidate sociotechnical imaginaries, including projected social order, feared/desirable futures, agents of change, beneficiaries or harmed groups, and ownership/control/governance assumptions. Do not claim stabilization from a single document."
    system_id, task_id = prompt_ids_for_stage(project_profile, "discourse")
    system_resource = load_prompt(system_id, version="v1")
    task_resource = load_prompt(task_id, version="v1")
    rendered_task = task_resource.render(project_note=project_note)
    envelope = _envelope(record, context, task=rendered_task.text, codebook_entries=codebook_entries, prompt_version=prompt_version)
    proposal, response = chat_structured(provider, DiscourseProposal, model=model, system_prompt=system_resource.text, user_prompt=envelope.render(), allow_cloud_fallback=allow_cloud_fallback)
    prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
    run_meta = _model_run_metadata(context, response, prompt_meta, prompt_version=prompt_version, stage="discourse")
    _append_stage(record, "discourse_analysis", {"created_at": datetime.now(UTC).isoformat(), "prompt_version": prompt_version, **prompt_meta, "context_provenance": envelope.provenance_snapshot(), "proposal": proposal.model_dump(mode="json"), "model_run": run_meta})
    record.analysis.model_runs.append(run_meta)
    return proposal


def _relation_chains(record: CanonicalRecord, relations: list[DiscursiveRelation], chain_type: Literal["equivalence", "difference"]) -> list[RelationChain]:
    chains: list[RelationChain] = []
    for index, item in enumerate(relations, start=1):
        source = item.source.strip()
        target = item.target.strip()
        if not source or not target:
            continue
        member_refs = [source] if source == target else [source, target]
        if len(member_refs) < 2:
            continue
        chains.append(RelationChain(chain_id=f"{chain_type}_chain:{len(chains) + 1}", chain_type=chain_type, member_refs=member_refs, evidence_ids=_evidence_ids(record, item.evidence, f"{chain_type}_chain:{index}"), review_status="PROVISIONAL"))
    return chains


def _evidence_ids(record: CanonicalRecord, quotes: list[str], prefix: str) -> list[str]:
    ids: list[str] = []
    for quote in quotes:
        text = quote.strip()
        if not text:
            continue
        evidence_id = f"{prefix}:evidence:{len(record.evidence) + 1}"
        record.evidence.append(Evidence(evidence_id=evidence_id, kind="llm_proposed_source_evidence", source_url=record.source_url, quote=text, metadata={"review_status": "PROVISIONAL"}))
        ids.append(evidence_id)
    return ids


def _objects(record: CanonicalRecord, items: list[DiscursiveElement], kind: str) -> list[DiscourseObject]:
    validation_required = kind in {"floating_signifier", "empty_signifier", "formation", "imaginary"}
    return [DiscourseObject(object_id=f"{kind}:{index}", label=item.label, kind=kind, evidence_ids=_evidence_ids(record, item.evidence, f"{kind}:{index}"), confidence=item.confidence, uncertainty=item.uncertainty or None, review_status="PROVISIONAL", metadata={"corpus_validation_required": validation_required}) for index, item in enumerate(items, start=1)]


def postprocess_record(record: CanonicalRecord, summary: SummaryResult, discourse: DiscourseProposal, *, project_config: dict[str, Any] | None = None) -> CanonicalRecord:
    config = project_config or {}
    record.analysis.status = "analyzed"
    record.analysis.summary = summary.summary
    if stage_enabled(config, "entities"):
        record.analysis.entities = [Entity(entity_id=f"entity:{index}", label=label, review_status="PROVISIONAL") for index, label in enumerate(summary.entities, start=1)]
    else:
        record.analysis.entities = []
    if stage_enabled(config, "topics"):
        record.analysis.topics = [Topic(topic_id=f"summary-topic:{index}", canonical_label=label, metadata={"source": "summary_stage", "review_status": "PROVISIONAL"}) for index, label in enumerate(summary.topics, start=1) if label.strip()]
    else:
        record.analysis.topics = []
    if stage_enabled(config, "sentiment"):
        record.analysis.sentiments = [DiscourseObject(object_id=f"sentiment:{index}", label=label, kind="sentiment", review_status="PROVISIONAL") for index, label in enumerate(summary.sentiment_observations, start=1) if label.strip()]
    else:
        record.analysis.sentiments = []

    record.analysis.signifiers = []
    record.analysis.floating_signifiers = _objects(record, discourse.floating_signifier_candidates, "floating_signifier")
    record.analysis.empty_signifier_candidates = _objects(record, discourse.empty_signifier_candidates, "empty_signifier")
    if isinstance(summary, SummaryProposal):
        summary_signifiers = [DiscursiveElement(label=label, uncertainty="summary-stage candidate") for label in summary.candidate_signifiers]
        record.analysis.signifiers = _objects(record, summary_signifiers, "signifier")
    record.analysis.signifiers.extend(record.analysis.floating_signifiers)
    record.analysis.signifiers.extend(record.analysis.empty_signifier_candidates)
    record.analysis.nodal_points = _objects(record, discourse.nodal_point_candidates, "nodal_point")
    record.analysis.formations = _objects(record, discourse.formation_candidates, "formation")
    record.analysis.imaginaries = _objects(record, discourse.imaginary_candidates, "imaginary")
    record.analysis.us = _objects(record, discourse.collective_subjects, "collective_subject")
    record.analysis.frontier = _objects(record, discourse.frontiers, "frontier")
    record.analysis.affects = _objects(record, discourse.affects, "affect")
    record.analysis.formula_of_populism = {"populist": discourse.populist, "non_populist_reason": discourse.non_populist_reason, **discourse.formula_of_populism}
    record.analysis.uncertainty = list(dict.fromkeys(summary.uncertainty + discourse.uncertainty))
    record.analysis.abstentions = discourse.abstentions
    record.analysis.equivalence_chains = _relation_chains(record, discourse.equivalences, "equivalence")
    record.analysis.difference_chains = _relation_chains(record, discourse.differences, "difference")
    record.analysis.antagonisms = [Relation(relation_id=f"antagonism:{index}", relation_type=relation.relation_type, source_ref=relation.source, target_ref=relation.target, evidence_ids=_evidence_ids(record, relation.evidence, f"antagonism:{index}"), review_status="PROVISIONAL") for index, relation in enumerate(discourse.antagonisms, start=1)]
    relations = discourse.articulations + discourse.equivalences + discourse.differences + discourse.antagonisms
    record.analysis.relations = [Relation(relation_id=f"relation:{index}", relation_type=relation.relation_type, source_ref=relation.source, target_ref=relation.target, evidence_ids=_evidence_ids(record, relation.evidence, f"relation:{index}"), review_status="PROVISIONAL") for index, relation in enumerate(relations, start=1)]
    record.analysis.completed_at = datetime.now(UTC)
    return ensure_research_layers(record)


def build_discourse_graph(record: CanonicalRecord) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [{"id": record.source_url, "type": "document", "label": record.content.title or record.source_url}]
    edges: list[dict[str, Any]] = []
    node_ids = {record.source_url}
    label_to_id: dict[str, str] = {}
    groups = (("signifier", record.analysis.signifiers), ("collective_subject", record.analysis.us), ("frontier", record.analysis.frontier), ("affect", record.analysis.affects), ("formation", record.analysis.formations), ("imaginary", record.analysis.imaginaries), ("nodal_point", record.analysis.nodal_points))
    for node_type, objects in groups:
        for obj in objects:
            nodes.append({"id": obj.object_id, "type": node_type, "label": obj.label, "confidence": obj.confidence, "review_status": obj.review_status, "evidence_ids": obj.evidence_ids, "metadata": obj.metadata})
            node_ids.add(obj.object_id)
            label_to_id.setdefault(obj.label.casefold(), obj.object_id)
            edges.append({"source": record.source_url, "target": obj.object_id, "type": "CANDIDATE_IN"})
    relation_map = {"articulation": "ARTICULATES", "equivalence": "EQUIVALENT_TO", "difference": "DIFFERENTIATED_FROM", "antagonism": "ANTAGONISTIC_TO"}
    for rel in record.analysis.relations:
        source = label_to_id.get(rel.source_ref.casefold(), rel.source_ref)
        target = label_to_id.get(rel.target_ref.casefold(), rel.target_ref)
        for endpoint in (source, target):
            if endpoint not in node_ids:
                nodes.append({"id": endpoint, "type": "concept", "label": endpoint, "review_status": "PROVISIONAL"})
                node_ids.add(endpoint)
        edges.append({"source": source, "target": target, "type": relation_map.get(rel.relation_type.lower(), rel.relation_type.upper()), "review_status": rel.review_status, "evidence_ids": rel.evidence_ids})
    return {"schema": "laclaugpt-discourse-graph-v1", "source_url": record.source_url, "nodes": nodes, "edges": edges}


def run_canonical_pipeline(record: CanonicalRecord, *, provider, context: PipelineContext | None = None, codebook_entries: list[CodebookEntry] | None = None, preprocessor: Preprocessor | None = None, graph_sink: GraphSink | None = None, vector_sink: VectorSink | None = None, model: str = "auto", project_profile: str = "generic", prompt_version: str = "canonical-pipeline-v1", allow_cloud_fallback: bool | None = None) -> CanonicalRecord:
    ctx = context or PipelineContext()
    entries = codebook_entries or []
    contract = resolve_stage_contract(ctx.project_config) if ctx.project_config else {"enabled_flags": [], "disabled_flags": [], "statuses": {}, "runtime_stages": [], "output_fields": {}}
    _append_stage(record, "effective_stage_contract", {"created_at": datetime.now(UTC).isoformat(), "project_config_revision": ctx.project_config_revision, "project_config_sha256": _project_config_sha256(ctx), **contract})
    record.analysis.started_at = record.analysis.started_at or datetime.now(UTC)
    preprocess_record(record, preprocessor=preprocessor)
    if stage_enabled(ctx.project_config, "multimodal"):
        analyze_frames(record, provider=provider, context=ctx, codebook_entries=entries, model=model, prompt_version=f"{prompt_version}:frame", project_profile=project_profile, allow_cloud_fallback=allow_cloud_fallback)
    summary = summarize_record(record, provider=provider, context=ctx, codebook_entries=entries, model=model, prompt_version=f"{prompt_version}:summary", project_profile=project_profile, allow_cloud_fallback=allow_cloud_fallback)
    if stage_enabled(ctx.project_config, "laclau"):
        discourse = discourse_analysis(record, provider=provider, context=ctx, codebook_entries=entries, model=model, prompt_version=f"{prompt_version}:discourse", project_profile=project_profile, allow_cloud_fallback=allow_cloud_fallback)
    else:
        discourse = DiscourseProposal()
    run_optional_critical_ai(record, provider=provider, context=ctx, codebook_entries=entries, model=model, allow_cloud_fallback=allow_cloud_fallback)
    postprocess_record(record, summary, discourse, project_config=ctx.project_config)
    graph = build_discourse_graph(record)
    _append_stage(record, "discourse_graph", graph)
    if graph_sink:
        graph_sink.write_graph(record.source_url, graph)
    if vector_sink:
        vector_sink.upsert(record.source_url, record.human_readable.markdown or record.content.text, {"source_url": record.source_url, "project_profile": project_profile})
    return record
