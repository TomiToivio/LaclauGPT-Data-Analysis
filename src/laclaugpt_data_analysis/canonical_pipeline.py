"""Canonical staged LaclauGPT analysis orchestration.

The orchestration preserves the legacy multimodal/human-readable ladder while using
current evidence-first discourse-analysis contracts. Expensive preprocessing remains
pluggable so the same pipeline can run on a laptop, CSC Roihu, or a Linux server.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord, DiscourseObject, Entity, Evidence, Relation
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
    lines = []
    for entry in entries:
        aliases = ", ".join(entry.aliases)
        lines.append(
            f"- {entry.kind}: {entry.label}" + (f" (aliases: {aliases})" if aliases else "")
        )
    return "\n".join(lines)


def _envelope(
    record: CanonicalRecord,
    context: PipelineContext,
    *,
    task: str,
    codebook_entries: list[CodebookEntry],
    prompt_version: str,
) -> PromptEnvelope:
    memory = "\n".join(
        part for part in (context.memory_context, _memory_text(codebook_entries)) if part
    )
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
    """Stage 1: merge deterministic/NLP/multimodal enrichment without data loss."""
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
    """Stage 2: analyse each canonical frame/image independently."""
    if not record.content.frames:
        return record
    for frame in record.content.frames:
        if project_profile.lower() == "ep24":
            profile_note = (
                "EP24: preserve legacy election visual categories: framing, scene, activity, "
                "objects, subjects, flags/symbols, platform cues and visible text."
            )
        else:
            profile_note = (
                "AI26/generic AI: also inspect labs/models/demos/data centres/robots/LLM "
                "interfaces, AI-generated media, corporate/policy material, protests, charts "
                "and candidate future-oriented AI signifiers. Do not perform final discourse "
                "classification here."
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
        record.intermediate.frame_analysis.append(
            {
                "frame_id": frame.id,
                "timestamp_seconds": frame.timestamp_seconds,
                "analysis": proposal.model_dump(mode="json"),
                "prompt_version": prompt_version,
                "context_provenance": envelope.provenance_snapshot(),
                "model_run": response.provenance.to_dict(),
            }
        )
        record.analysis.model_runs.append(
            {
                **response.provenance.to_dict(),
                "prompt_version": prompt_version,
                "stage": "frame",
            }
        )
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
    """Stage 3: human-readable summary and generic social-data-science pre-analysis."""
    task = """Create a human-readable synthesis of the complete item. Combine source metadata,
text, transcripts/translations, OCR, frame analyses and deterministic NLP outputs. Give a
narrative summary, topics, entities, sentiment observations for comparison with conventional
NLP, claims/demands/grievances, difficult language and event/time/location candidates. Add
only a light Laclaudian pre-analysis of candidate signifiers/articulations/subjects/frontiers.
Do not promote document-level candidates to corpus-level findings."""
    if project_profile.lower() == "ai26":
        task += """ For AI26 also record claims about what AI is/can do, desirable and feared
futures, sociotechnical-imaginary candidates, and ownership/control/governance assumptions.
A personal prediction is not by itself an institutionally stabilized imaginary."""
    envelope = _envelope(
        record,
        context,
        task=task,
        codebook_entries=codebook_entries,
        prompt_version=prompt_version,
    )
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
            "sociotechnical_imaginaries": "\n".join(
                proposal.sociotechnical_imaginary_candidates
            ),
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
    record.analysis.model_runs.append(
        {
            **response.provenance.to_dict(),
            "prompt_version": prompt_version,
            "stage": "summary",
        }
    )
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
    """Stage 4: dedicated evidence-first Laclau/Mouffe/Palonen pre-analysis."""
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
    envelope = _envelope(
        record,
        context,
        task=task,
        codebook_entries=codebook_entries,
        prompt_version=prompt_version,
    )
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
    record.analysis.model_runs.append(
        {
            **response.provenance.to_dict(),
            "prompt_version": prompt_version,
            "stage": "discourse",
        }
    )
    return proposal


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


def _objects(
    record: CanonicalRecord,
    items: list[DiscursiveElement],
    kind: str,
) -> list[DiscourseObject]:
    validation_required = kind in {
        "floating_signifier",
        "empty_signifier",
        "formation",
        "imaginary",
    }
    return [
        DiscourseObject(
            object_id=f"{kind}:{index}",
            label=item.label,
            kind=kind,
            evidence_ids=_evidence_ids(record, item.evidence, f"{kind}:{index}"),
            confidence=item.confidence,
            uncertainty=item.uncertainty or None,
            review_status="PROVISIONAL",
            metadata={"corpus_validation_required": validation_required},
        )
        for index, item in enumerate(items, start=1)
    ]


def postprocess_record(
    record: CanonicalRecord,
    summary: SummaryProposal,
    discourse: DiscourseProposal,
) -> CanonicalRecord:
    """Stage 5: validated stage outputs -> canonical record without discarding prose."""
    record.analysis.status = "analyzed"
    record.analysis.summary = summary.summary
    record.analysis.entities = [
        Entity(entity_id=f"entity:{index}", label=label, review_status="PROVISIONAL")
        for index, label in enumerate(summary.entities, start=1)
    ]

    summary_signifiers = [
        DiscursiveElement(label=label, uncertainty="summary-stage candidate")
        for label in summary.candidate_signifiers
    ]
    record.analysis.signifiers = _objects(record, summary_signifiers, "signifier")
    record.analysis.signifiers.extend(
        _objects(record, discourse.floating_signifier_candidates, "floating_signifier")
    )
    record.analysis.signifiers.extend(
        _objects(record, discourse.empty_signifier_candidates, "empty_signifier")
    )
    record.analysis.nodal_points = _objects(record, discourse.nodal_point_candidates, "nodal_point")
    record.analysis.formations = _objects(record, discourse.formation_candidates, "formation")
    record.analysis.imaginaries = _objects(record, discourse.imaginary_candidates, "imaginary")
    record.analysis.us = _objects(record, discourse.collective_subjects, "collective_subject")
    record.analysis.frontier = _objects(record, discourse.frontiers, "frontier")
    record.analysis.affects = _objects(record, discourse.affects, "affect")
    record.analysis.formula_of_populism = {
        "populist": discourse.populist,
        "non_populist_reason": discourse.non_populist_reason,
        **discourse.formula_of_populism,
    }
    record.analysis.uncertainty = list(
        dict.fromkeys(summary.uncertainty + discourse.uncertainty)
    )
    record.analysis.abstentions = discourse.abstentions

    relations = (
        discourse.articulations
        + discourse.equivalences
        + discourse.differences
        + discourse.antagonisms
    )
    record.analysis.relations = [
        Relation(
            relation_id=f"relation:{index}",
            relation_type=relation.relation_type,
            source_ref=relation.source,
            target_ref=relation.target,
            evidence_ids=_evidence_ids(record, relation.evidence, f"relation:{index}"),
            review_status="PROVISIONAL",
        )
        for index, relation in enumerate(relations, start=1)
    ]
    record.analysis.completed_at = datetime.now(UTC)
    return ensure_research_layers(record)


def build_discourse_graph(record: CanonicalRecord) -> dict[str, Any]:
    """Stage 6: storage-neutral projection using canonical graph semantics."""
    nodes: list[dict[str, Any]] = [
        {
            "id": record.source_url,
            "type": "document",
            "label": record.content.title or record.source_url,
        }
    ]
    edges: list[dict[str, Any]] = []
    node_ids = {record.source_url}
    label_to_id: dict[str, str] = {}
    groups = (
        ("signifier", record.analysis.signifiers),
        ("collective_subject", record.analysis.us),
        ("frontier", record.analysis.frontier),
        ("affect", record.analysis.affects),
        ("formation", record.analysis.formations),
        ("imaginary", record.analysis.imaginaries),
        ("nodal_point", record.analysis.nodal_points),
    )
    for node_type, objects in groups:
        for obj in objects:
            nodes.append(
                {
                    "id": obj.object_id,
                    "type": node_type,
                    "label": obj.label,
                    "confidence": obj.confidence,
                    "review_status": obj.review_status,
                    "evidence_ids": obj.evidence_ids,
                    "metadata": obj.metadata,
                }
            )
            node_ids.add(obj.object_id)
            label_to_id.setdefault(obj.label.casefold(), obj.object_id)
            edges.append(
                {
                    "source": record.source_url,
                    "target": obj.object_id,
                    "type": "CANDIDATE_IN",
                }
            )

    relation_map = {
        "articulation": "ARTICULATES",
        "equivalence": "EQUIVALENT_TO",
        "difference": "DIFFERENTIATED_FROM",
        "antagonism": "ANTAGONISTIC_TO",
    }
    for rel in record.analysis.relations:
        source = label_to_id.get(rel.source_ref.casefold(), rel.source_ref)
        target = label_to_id.get(rel.target_ref.casefold(), rel.target_ref)
        for endpoint in (source, target):
            if endpoint not in node_ids:
                nodes.append(
                    {
                        "id": endpoint,
                        "type": "concept",
                        "label": endpoint,
                        "review_status": "PROVISIONAL",
                    }
                )
                node_ids.add(endpoint)
        edges.append(
            {
                "source": source,
                "target": target,
                "type": relation_map.get(
                    rel.relation_type.lower(), rel.relation_type.upper()
                ),
                "review_status": rel.review_status,
                "evidence_ids": rel.evidence_ids,
            }
        )
    return {
        "schema": "laclaugpt-discourse-graph-v1",
        "source_url": record.source_url,
        "nodes": nodes,
        "edges": edges,
    }


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
    """Run stages 1-6; aggregate reports and exports operate on the resulting corpus."""
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
