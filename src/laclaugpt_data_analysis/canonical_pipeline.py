"""End-to-end staged analysis pipeline preserving legacy and LaclauGPT 2.0 layers.

This module intentionally orchestrates existing NLP/multimodal backends rather than
hard-coding Whisper/OpenCV/spaCy/provider dependencies. Expensive preprocessors can run
locally, on CSC Roihu, or on a server and feed their results into the same canonical
record. Every LLM stage uses the shared eight-part prompt envelope.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Protocol

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord, DiscourseObject, Entity, Relation
from .codebooks import CodebookEntry
from .context_envelope import PromptEnvelope, build_prompt_envelope
from .llm.structured_output import chat_structured
from .research_record import ensure_research_layers


THEORY_GUARDRAILS = """Use evidence-first LaclauGPT methodology. Document-level outputs are provisional.
Frequency is not hegemony. Polysemy is not empty signification. Negativity is not
antagonism. Sentiment is not affective investment. Floating/empty signifier,
ideological-formation and hegemony claims require corpus-level validation. Abstention
and empty lists are valid. Codebooks, memory and RAG are context, never source evidence."""


class PipelineContext(BaseModel):
    project_context: str = ""
    source_context: str = ""
    situational_context: str = ""
    memory_context: str = ""
    rag_context: str = ""
    provenance: dict[str, list[str]] = Field(default_factory=dict)


class FrameProposal(BaseModel):
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


class EventCandidate(BaseModel):
    description: str = ""
    time: str = ""
    location: str = ""
    actors: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)


class SummaryProposal(BaseModel):
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


def _append_stage(record: CanonicalRecord, name: str, payload: dict[str, Any]) -> None:
    existing = record.intermediate.stage_outputs.get(name)
    history = existing if isinstance(existing, list) else ([] if existing is None else [existing])
    history.append(payload)
    record.intermediate.stage_outputs[name] = history


def _memory_text(entries: list[CodebookEntry]) -> str:
    if not entries:
        return ""
    lines = []
    for entry in entries:
        aliases = ", ".join(entry.aliases)
        lines.append(f"- {entry.kind}: {entry.label}" + (f" (aliases: {aliases})" if aliases else ""))
    return "\n".join(lines)


def _envelope(
    record: CanonicalRecord,
    context: PipelineContext,
    *,
    task: str,
    codebook_entries: list[CodebookEntry],
    prompt_version: str,
) -> PromptEnvelope:
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


def preprocess_record(
    record: CanonicalRecord,
    *,
    preprocessor: Preprocessor | None = None,
) -> CanonicalRecord:
    """Stage 1: preserve source and merge deterministic/NLP/multimodal enrichment.

    A preprocessor may return canonical keys ``asr``, ``ocr``, ``frames``,
    ``translations``, ``legacy`` and arbitrary ``stage_output``. Unknown raw source
    fields remain in ``raw_capture`` / ``source.raw_metadata``.
    """
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
    _append_stage(
        record,
        "preprocess_contract",
        {
            "created_at": datetime.now(UTC).isoformat(),
            "source_preserved": record.raw_capture.preserved or bool(record.source.raw_metadata),
            "legacy_fields_preserved": sorted(record.legacy),
        },
    )
    return record


def analyze_frames(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext,
    codebook_entries: list[CodebookEntry],
    model: str,
    prompt_version: str,
    project_profile: str,
    allow_cloud_fallback: bool | None,
) -> CanonicalRecord:
    """Stage 2: analyse each existing canonical frame/image independently."""
    if not record.content.frames:
        return record
    for frame in record.content.frames:
        profile_note = (
            "EP24: preserve the legacy election visual categories: framing, scene, activity, "
            "objects, subjects, flags/symbols, screen-recording/platform cues and visible text."
            if project_profile.lower() == "ep24"
            else "AI26: also inspect AI labs/models/demos/data centres/robots/LLM interfaces, "
            "AI-generated media, corporate/policy material, protests, charts and candidate "
            "future-oriented AI signifiers. Do not perform final discourse classification here."
        )
        task = f"""Analyse frame {frame.id} at {frame.timestamp_seconds} seconds.
{profile_note}
Extract usernames/handles and other visible text when supported. Treat uncertain visual
identifications as uncertain. Candidate signifiers are provisional only."""
        envelope = _envelope(
            record,
            context,
            task=task,
            codebook_entries=codebook_entries,
            prompt_version=prompt_version,
        )
        proposal, response = chat_structured(
            provider,
            FrameProposal,
            model=model,
            system_prompt=THEORY_GUARDRAILS,
            user_prompt=envelope.render(),
            allow_cloud_fallback=allow_cloud_fallback,
        )
        item = {
            "frame_id": frame.id,
            "timestamp_seconds": frame.timestamp_seconds,
            "analysis": proposal.model_dump(mode="json"),
            "prompt_version": prompt_version,
            "context_provenance": envelope.provenance_snapshot(),
            "model_run": response.provenance.to_dict(),
        }
        record.intermediate.frame_analysis.append(item)
        record.analysis.model_runs.append({**response.provenance.to_dict(), "prompt_version": prompt_version, "stage": "frame"})
    return record


def summarize_record(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext,
    codebook_entries: list[CodebookEntry],
    model: str,
    prompt_version: str,
    project_profile: str,
    allow_cloud_fallback: bool | None,
) -> SummaryProposal:
    """Stage 3: researcher-readable generic summary/NLP comparison layer."""
    ai26 = project_profile.lower() == "ai26"
    task = """Create a human-readable synthesis of the complete item. Combine source metadata,
text, transcripts/translations, OCR, frame analyses and deterministic NLP outputs. Give a
narrative summary, topics, entities, sentiment observations for comparison with conventional
NLP, claims/demands/grievances, difficult language and event/time/location candidates. Add
only a light Laclaudian pre-analysis of candidate signifiers/articulations/subjects/frontiers.
Do not promote document-level candidates to corpus-level findings."""
    if ai26:
        task += """ For AI26 also record claims about what AI is/can do, desirable and feared
futures, sociotechnical-imaginary candidates, and ownership/control/governance assumptions.
A personal prediction is not by itself an institutionally stabilized imaginary."""
    envelope = _envelope(record, context, task=task, codebook_entries=codebook_entries, prompt_version=prompt_version)
    proposal, response = chat_structured(
        provider,
        SummaryProposal,
        model=model,
        system_prompt=THEORY_GUARDRAILS,
        user_prompt=envelope.render(),
        allow_cloud_fallback=allow_cloud_fallback,
    )
    now = datetime.now(UTC).isoformat()
    record.human_readable.summary = proposal.summary
    record.human_readable.markdown = proposal.narrative or proposal.summary
    record.human_readable.generated_at = now
    record.human_readable.sections.update(
        {
            "narrative": proposal.narrative,
            "topics": "\n".join(proposal.topics),
            "entities": "\n".join(proposal.entities),
            "sentiment": "\n".join(proposal.sentiment_observations),
            "claims": "\n".join(proposal.claims),
            "demands": "\n".join(proposal.demands),
            "grievances": "\n".join(proposal.grievances),
            "candidate_signifiers": "\n".join(proposal.candidate_signifiers),
            "sociotechnical_imaginaries": "\n".join(proposal.sociotechnical_imaginary_candidates),
        }
    )
    _append_stage(
        record,
        "summary_preanalysis",
        {
            "created_at": now,
            "prompt_version": prompt_version,
            "context_provenance": envelope.provenance_snapshot(),
            "proposal": proposal.model_dump(mode="json"),
            "model_run": response.provenance.to_dict(),
        },
    )
    record.analysis.model_runs.append({**response.provenance.to_dict(), "prompt_version": prompt_version, "stage": "summary"})
    return proposal


def discourse_analysis(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext,
    codebook_entries: list[CodebookEntry],
    model: str,
    prompt_version: str,
    project_profile: str,
    allow_cloud_fallback: bool | None,
) -> DiscourseProposal:
    """Stage 4: evidence-first Laclaudian/Palonen discourse pre-analysis."""
    task = """Perform the dedicated Laclau/Mouffe/Palonen discourse pre-analysis. Identify only
evidence-supported demands, articulations, equivalence/difference relations, collective
subjects, constitutive antagonistic frontiers, affective investments, and provisional nodal,
floating/empty-signifier and formation candidates. Distinguish generic sentiment from affective
investment. Return counter-evidence, uncertainty and abstentions. Populism requires both a
constructed collective Us and a constitutive antagonistic Frontier; anti-elite language alone is
not enough. All floating/empty signifier and formation outputs are candidates pending corpus
validation."""
    if project_profile.lower() == "ai26":
        task += """ Also identify evidence-supported candidate sociotechnical imaginaries,
including projected social order, feared/desirable futures, agents of change, beneficiaries or
harmed groups, and ownership/control/governance assumptions. Do not claim stabilization from a
single document."""
    envelope = _envelope(record, context, task=task, codebook_entries=codebook_entries, prompt_version=prompt_version)
    proposal, response = chat_structured(
        provider,
        DiscourseProposal,
        model=model,
        system_prompt=THEORY_GUARDRAILS,
        user_prompt=envelope.render(),
        allow_cloud_fallback=allow_cloud_fallback,
    )
    _append_stage(
        record,
        "discourse_analysis",
        {
            "created_at": datetime.now(UTC).isoformat(),
            "prompt_version": prompt_version,
            "context_provenance": envelope.provenance_snapshot(),
            "proposal": proposal.model_dump(mode="json"),
            "model_run": response.provenance.to_dict(),
        },
    )
    record.analysis.model_runs.append({**response.provenance.to_dict(), "prompt_version": prompt_version, "stage": "discourse"})
    return proposal


def _objects(items: list[DiscursiveElement], kind: str) -> list[DiscourseObject]:
    return [
        DiscourseObject(
            object_id=f"{kind}:{index}",
            label=item.label,
            kind=kind,
            confidence=item.confidence,
            uncertainty=item.uncertainty or None,
            review_status="PROVISIONAL",
            metadata={"evidence_text": item.evidence, "corpus_validation_required": kind in {"floating_signifier", "empty_signifier", "formation", "imaginary"}},
        )
        for index, item in enumerate(items, start=1)
    ]


def postprocess_record(record: CanonicalRecord, summary: SummaryProposal, discourse: DiscourseProposal) -> CanonicalRecord:
    """Stage 5: strict Pydantic outputs -> canonical machine-readable record, without data loss."""
    record.analysis.status = "analyzed"
    record.analysis.summary = summary.summary
    record.analysis.entities = [Entity(entity_id=f"entity:{i}", label=x, review_status="PROVISIONAL") for i, x in enumerate(summary.entities, 1)]
    record.analysis.signifiers = _objects(
        [DiscursiveElement(label=x, confidence=0.0, uncertainty="summary-stage candidate") for x in summary.candidate_signifiers],
        "signifier",
    )
    record.analysis.nodal_points = _objects(discourse.nodal_point_candidates, "nodal_point")
    record.analysis.formations = _objects(discourse.formation_candidates, "formation")
    record.analysis.imaginaries = _objects(discourse.imaginary_candidates, "imaginary")
    record.analysis.us = _objects(discourse.collective_subjects, "collective_subject")
    record.analysis.frontier = _objects(discourse.frontiers, "frontier")
    record.analysis.affects = _objects(discourse.affects, "affect")
    record.analysis.formula_of_populism = {
        "populist": discourse.populist,
        "non_populist_reason": discourse.non_populist_reason,
        **discourse.formula_of_populism,
    }
    record.analysis.uncertainty = list(dict.fromkeys(summary.uncertainty + discourse.uncertainty))
    record.analysis.abstentions = discourse.abstentions
    relations = discourse.articulations + discourse.equivalences + discourse.differences + discourse.antagonisms
    record.analysis.relations = [
        Relation(
            relation_id=f"relation:{i}",
            relation_type=rel.relation_type,
            source_ref=rel.source,
            target_ref=rel.target,
            review_status="PROVISIONAL",
        )
        for i, rel in enumerate(relations, 1)
    ]
    record.analysis.completed_at = datetime.now(UTC)
    return ensure_research_layers(record)


def build_discourse_graph(record: CanonicalRecord) -> dict[str, Any]:
    """Stage 6 projection using canonical LaclauGPT graph relation vocabulary.

    This is storage-neutral. An ArangoDB adapter can persist the same nodes/edges without
    changing the research-domain model.
    """
    nodes: list[dict[str, Any]] = [{"id": record.source_url, "type": "document", "label": record.content.title or record.source_url}]
    edges: list[dict[str, Any]] = []
    groups = (
        ("signifier", record.analysis.signifiers),
        ("collective_subject", record.analysis.us),
        ("frontier", record.analysis.frontier),
        ("affect", record.analysis.affects),
        ("formation", record.analysis.formations),
        ("imaginary", record.analysis.imaginaries),
    )
    for node_type, objects in groups:
        for obj in objects:
            nodes.append({
                "id": obj.object_id,
                "type": node_type,
                "label": obj.label,
                "confidence": obj.confidence,
                "review_status": obj.review_status,
                "metadata": obj.metadata,
            })
            edges.append({"source": record.source_url, "target": obj.object_id, "type": "CANDIDATE_IN"})
    relation_map = {
        "articulation": "ARTICULATES",
        "equivalence": "EQUIVALENT_TO",
        "difference": "DIFFERENTIATED_FROM",
        "antagonism": "ANTAGONISTIC_TO",
    }
    for rel in record.analysis.relations:
        edges.append({"source": rel.source_ref, "target": rel.target_ref, "type": relation_map.get(rel.relation_type.lower(), rel.relation_type.upper()), "review_status": rel.review_status})
    return {"schema": "laclaugpt-discourse-graph-v1", "source_url": record.source_url, "nodes": nodes, "edges": edges}


def run_canonical_pipeline(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext | None = None,
    codebook_entries: list[CodebookEntry] | None = None,
    preprocessor: Preprocessor | None = None,
    graph_sink: GraphSink | None = None,
    vector_sink: VectorSink | None = None,
    model: str = "auto",
    project_profile: str = "generic",
    prompt_version: str = "canonical-pipeline-v1",
    allow_cloud_fallback: bool | None = None,
) -> CanonicalRecord:
    """Run stages 1-6 in the legacy-compatible order; reporting/export are corpus operations."""
    ctx = context or PipelineContext()
    entries = codebook_entries or []
    record.analysis.started_at = record.analysis.started_at or datetime.now(UTC)
    preprocess_record(record, preprocessor=preprocessor)
    analyze_frames(
        record,
        provider=provider,
        context=ctx,
        codebook_entries=entries,
        model=model,
        prompt_version=f"{prompt_version}:frame",
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )
    summary = summarize_record(
        record,
        provider=provider,
        context=ctx,
        codebook_entries=entries,
        model=model,
        prompt_version=f"{prompt_version}:summary",
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )
    discourse = discourse_analysis(
        record,
        provider=provider,
        context=ctx,
        codebook_entries=entries,
        model=model,
        prompt_version=f"{prompt_version}:discourse",
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )
    postprocess_record(record, summary, discourse)
    graph = build_discourse_graph(record)
    _append_stage(record, "discourse_graph", graph)
    if graph_sink:
        graph_sink.write_graph(record.source_url, graph)
    if vector_sink:
        vector_sink.upsert(
            record.source_url,
            record.human_readable.markdown or record.content.text,
            {"source_url": record.source_url, "project_profile": project_profile},
        )
    return record
