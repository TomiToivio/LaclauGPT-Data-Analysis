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
from .llm.structured_output import chat_structured
from .models import Topic
from .modality_routing import (
    build_modality_plan,
    ensure_still_image_frames,
    legacy_multimodal_projection,
)
from .prompt_library import load_prompt, prompt_provenance
from .research_record import ensure_research_layers
from .social_semiotic import (
    MultimodalFrameProposal,
    MultimodalSummaryProposal,
    UncertaintyObservation,
    assert_preanalysis_boundary,
)

# Shortest quote that may count as verbatim evidence. Below this length a match
# is likely coincidence (a stray "AI" appears in almost any AI26 source), and a
# fragment masquerading as a substantiated quotation is worse than no evidence.
_MIN_QUOTE_CHARS = 12


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
    "sna": "phase2_optional",
    "ant": "phase2_optional",
    "valueflows": "phase2_optional",
}


def _analysis_flags(context: PipelineContext) -> dict[str, Any]:
    analysis = context.project_config.get("analysis") if context.project_config else None
    return dict(analysis) if isinstance(analysis, dict) else {}


_PHASE2_CAPABILITIES = frozenset({"sna", "ant", "valueflows", "dna_statement_coding", "critical_ai"})


def _analysis_phase(context: PipelineContext) -> int:
    value = context.project_config.get("analysis_phase", 1) if context.project_config else 1
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("analysis_phase must be an integer") from exc


def _phase_allows(context: PipelineContext, key: str) -> bool:
    return key not in _PHASE2_CAPABILITIES or _analysis_phase(context) >= 2


def _enabled(context: PipelineContext, key: str, *, default: bool = True) -> bool:
    flags = _analysis_flags(context)
    if key in flags:
        value = flags[key]
    elif key == "multimodal" and context.project_config and key in context.project_config:
        # Compatibility with the pre-analysis config shape used before
        # project_config.analysis became the canonical capability namespace.
        # It is still an explicit opt-in, never an inferred activation.
        value = context.project_config[key]
    else:
        value = default
    configured = bool(value.get("enabled", default)) if isinstance(value, dict) else bool(value)
    return configured and _phase_allows(context, key)


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
    phase = _analysis_phase(context)
    if phase < 1:
        raise ValueError("analysis_phase must be >= 1")


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
    if profile == "ep24":
        ep24_tasks = {
            "frame": ("laclau.system", "ep24.frame_analysis"),
            "summary": ("laclau.system", "ep24.summary_analysis"),
            "discourse": ("laclau.system", "ep24.laclau_analysis"),
        }
        if stage in ep24_tasks:
            return ep24_tasks[stage]
    if stage == "frame":
        return ("multimodal.system", "multimodal.frame_analysis") if profile == "ai26" else ("laclau.system", "laclau.frame_analysis")
    if stage == "summary":
        return ("multimodal.system", "multimodal.summary_analysis") if profile == "ai26" else ("laclau.system", "laclau.summary_analysis")
    if stage == "discourse":
        return "laclau.system", "laclau.discourse_analysis"
    raise ValueError(f"unsupported canonical pipeline stage: {stage}")


def _summary_markdown(proposal: MultimodalSummaryProposal) -> str:
    parts = [
        "# Multimodal social-semiotic pre-analysis",
        proposal.cross_modal_synthesis or proposal.narrative or proposal.summary,
    ]
    if proposal.intermodal_relations:
        relations = "\n".join(
            f"- {item.relation_type}: {item.description}"
            for item in proposal.intermodal_relations
        )
        parts.extend(("## Intermodal relations", relations))
    if proposal.limitations:
        parts.extend(("## Limitations", "\n".join(f"- {x}" for x in proposal.limitations)))
    return "\n\n".join(part for part in parts if part).strip()


def _summary_uncertainty(summary: SummaryResult) -> list[str]:
    values = getattr(summary, "uncertainty", [])
    return [
        item.description if isinstance(item, UncertaintyObservation) else str(item)
        for item in values
        if item
    ]


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
        _append_stage(record, "frame_analysis_skipped", {
            "created_at": datetime.now(UTC).isoformat(),
            "reason": "text_only_or_no_extracted_frames",
        })
        return record
    # Phase 1 is capability-driven: the presence of canonical visual units is
    # the activation gate. Text-only records have already returned above.
    system_id, task_id = prompt_ids_for_stage(project_profile, "frame")
    ai26_multimodal = project_profile.casefold() == "ai26"
    system_resource = load_prompt(system_id, version="v2" if ai26_multimodal else "v1")
    task_resource = load_prompt(
        task_id,
        version="v2" if (ai26_multimodal or project_profile.casefold() == "ep24") else "v1",
    )
    for frame in record.content.frames:
        rendered_task = task_resource.render(frame_id=frame.id, timestamp_seconds=frame.timestamp_seconds, project_note="AI26 relevance guide only" if ai26_multimodal else "Generic descriptive frame analysis.")
        envelope = _envelope(record, context, task=rendered_task.text, codebook_entries=codebook_entries, prompt_version=prompt_version)
        proposal_model = MultimodalFrameProposal if ai26_multimodal else FrameProposal
        proposal, response = chat_structured(provider, proposal_model, model=model, system_prompt=system_resource.text, user_prompt=envelope.render(), allow_cloud_fallback=allow_cloud_fallback)
        if ai26_multimodal:
            assert_preanalysis_boundary(proposal.model_dump(mode="json"))
        prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
        run_meta = _model_run_metadata(context, response, prompt_meta, prompt_version=prompt_version, stage="multimodal_frame" if ai26_multimodal else "frame")
        record.intermediate.frame_analysis.append({"frame_id": frame.id, "timestamp_seconds": frame.timestamp_seconds, "analysis": proposal.model_dump(mode="json"), "prompt_version": prompt_version, **prompt_meta, "context_provenance": envelope.provenance_snapshot(), "model_run": run_meta})
        record.analysis.model_runs.append(run_meta)
    return record


def summarize_record(record: CanonicalRecord, *, provider, context: PipelineContext, codebook_entries: list[CodebookEntry], model: str, prompt_version: str, project_profile: str, allow_cloud_fallback: bool | None) -> SummaryResult:
    ai26_multimodal = project_profile.casefold() == "ai26"
    system_id, task_id = prompt_ids_for_stage(project_profile, "summary")
    system_resource = load_prompt(system_id, version="v2" if ai26_multimodal else "v1")
    task_resource = load_prompt(
        task_id,
        version="v2" if (ai26_multimodal or project_profile.casefold() == "ep24") else "v1",
    )
    rendered_task = task_resource.render(project_note="AI26 multimodal/light sociology summary." if ai26_multimodal else "(none)")
    envelope = _envelope(record, context, task=rendered_task.text, codebook_entries=codebook_entries, prompt_version=prompt_version)
    proposal_model = MultimodalSummaryProposal if ai26_multimodal else SummaryProposal
    proposal, response = chat_structured(provider, proposal_model, model=model, system_prompt=system_resource.text, user_prompt=envelope.render(), allow_cloud_fallback=allow_cloud_fallback)
    if ai26_multimodal:
        assert_preanalysis_boundary(proposal.model_dump(mode="json"))
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
    task_resource = load_prompt(task_id, version="v2" if project_profile.casefold() == "ep24" else "v1")
    rendered_task = task_resource.render(project_note="AI26 discourse analysis." if project_profile.casefold() == "ai26" else "(none)")
    envelope = _envelope(record, context, task=rendered_task.text, codebook_entries=codebook_entries, prompt_version=prompt_version)
    proposal, response = chat_structured(provider, DiscourseProposal, model=model, system_prompt=system_resource.text, user_prompt=envelope.render(), allow_cloud_fallback=allow_cloud_fallback)
    prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered_task)
    run_meta = _model_run_metadata(context, response, prompt_meta, prompt_version=prompt_version, stage="discourse")
    _append_stage(record, "discourse_analysis", {"created_at": datetime.now(UTC).isoformat(), "prompt_version": prompt_version, **prompt_meta, "context_provenance": envelope.provenance_snapshot(), "proposal": proposal.model_dump(mode="json"), "model_run": run_meta})
    record.analysis.model_runs.append(run_meta)
    return proposal


def _locate_quote(source_text: str, quote: str) -> tuple[int | None, int | None]:
    """Locate ``quote`` in ``source_text``, tolerant of whitespace differences.

    Returns ``(start, end)`` offsets into ``source_text`` when the quote occurs
    verbatim (whitespace-normalised), otherwise ``(None, None)``.

    A model-proposed quote is evidence only when it can be pointed at in the
    source. Paraphrases are common, so callers must record the outcome rather
    than assume success; see ``_evidence_ids``.

    Quotes shorter than ``_MIN_QUOTE_CHARS`` are refused even when they match:
    a very short string occurs by chance and would let a fragment masquerade as
    a substantiated quotation.
    """
    if not source_text or not quote:
        return None, None
    if len(quote.strip()) < _MIN_QUOTE_CHARS:
        return None, None

    # Direct hit first: the cheap, exact case.
    exact_start = source_text.find(quote)
    if exact_start >= 0:
        return exact_start, exact_start + len(quote)

    # Whitespace-normalised hit: models re-wrap and collapse spaces. Build a
    # normalised index that maps each normalised character back to its offset,
    # so the returned span still slices the ORIGINAL text.
    normalised_chars: list[str] = []
    positions: list[int] = []
    previous_space = False
    for index, char in enumerate(source_text):
        if char.isspace():
            if previous_space:
                continue
            normalised_chars.append(" ")
            positions.append(index)
            previous_space = True
        else:
            normalised_chars.append(char.lower())
            positions.append(index)
            previous_space = False
    normalised_source = "".join(normalised_chars)
    normalised_quote = " ".join(quote.split()).lower()
    if not normalised_quote:
        return None, None

    start = normalised_source.find(normalised_quote)
    if start < 0:
        return None, None
    end = start + len(normalised_quote) - 1
    if end >= len(positions):
        return None, None
    return positions[start], positions[end] + 1

def _evidence_ids(record: CanonicalRecord, quotes: list[str], prefix: str) -> list[str]:
    """Attach evidence, verifying each quote against the source.

    Policy: flag-and-count. ``exact=True`` with offsets when the quote is found
    in the source text; ``exact=False`` when it is not. A non-verbatim quote is
    never dropped silently — that would hide the rate at which the model
    paraphrases instead of quoting, and it would destroy the audit trail.
    """
    ids: list[str] = []
    source_text = record.content.text or ""
    for quote in quotes:
        text = quote.strip()
        if not text:
            continue
        evidence_id = f"{prefix}:evidence:{len(record.evidence) + 1}"
        start, end = _locate_quote(source_text, text)
        exact = start is not None and end is not None
        record.evidence.append(
            Evidence(
                evidence_id=evidence_id,
                kind="llm_proposed_source_evidence",
                source_url=record.source_url,
                quote=text,
                start_offset=start if exact else None,
                end_offset=end if exact else None,
                metadata={"review_status": "PROVISIONAL", "exact": exact},
            )
        )
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
    record.analysis.uncertainty = list(dict.fromkeys(_summary_uncertainty(summary) + discourse.uncertainty))
    record.analysis.abstentions = discourse.abstentions
    record.analysis.equivalence_chains = _relation_chains(record, discourse.equivalences, "equivalence")
    record.analysis.difference_chains = _relation_chains(record, discourse.differences, "difference")
    record.analysis.antagonisms = [Relation(relation_id=f"antagonism:{i}", relation_type=item.relation_type, source_ref=item.source, target_ref=item.target, evidence_ids=_evidence_ids(record, item.evidence, f"antagonism:{i}"), review_status="PROVISIONAL") for i, item in enumerate(discourse.antagonisms, start=1)]
    relations = discourse.articulations + discourse.equivalences + discourse.differences + discourse.antagonisms
    record.analysis.relations = [Relation(relation_id=f"relation:{i}", relation_type=item.relation_type, source_ref=item.source, target_ref=item.target, evidence_ids=_evidence_ids(record, item.evidence, f"relation:{i}"), review_status="PROVISIONAL") for i, item in enumerate(relations, start=1)]
    _append_stage(record, "postprocess", {
        "created_at": datetime.now(UTC).isoformat(),
        "schema": "canonical-analysis-v1",
        "validated": True,
        "source_stages": ["summary", "discourse"],
        "topics": [item.canonical_label for item in record.analysis.topics],
        "entities": [item.label for item in record.analysis.entities],
        "sentiments": [item.label for item in record.analysis.sentiments],
        "uncertainty": record.analysis.uncertainty,
    })
    _append_stage(record, "effective_analysis_stages", {"stages": _effective_stage_set(ctx), "project_config_revision": ctx.project_config_revision, "project_config_sha256": _project_config_sha256(ctx)})
    record.analysis.completed_at = datetime.now(UTC)
    return ensure_research_layers(record)


def build_discourse_graph(record: CanonicalRecord) -> dict[str, Any]:
    """Project Phase 1 canonical discourse objects into a portable evidence graph.

    The graph is deliberately a projection, not a second ontology. Canonical object
    and relation IDs remain stable, while evidence is represented explicitly so
    GraphML/GEXF exports can retain the audit topology.
    """
    nodes: list[dict[str, Any]] = [
        {
            "id": record.source_url,
            "type": "document",
            "label": record.content.title or record.source_url,
        }
    ]
    edges: list[dict[str, Any]] = []

    for evidence in record.evidence:
        nodes.append(
            {
                "id": evidence.evidence_id,
                "type": "evidence",
                "label": evidence.quote or evidence.ref or evidence.evidence_id,
                "kind": evidence.kind,
                "provenance_id": evidence.provenance_id,
            }
        )
        edges.append(
            {
                "id": f"evidence-in:{evidence.evidence_id}",
                "source": evidence.evidence_id,
                "target": record.source_url,
                "type": "EVIDENCE_IN",
            }
        )

    object_groups = [
        record.analysis.entities,
        record.analysis.topics,
        record.analysis.signifiers,
        record.analysis.nodal_points,
        record.analysis.floating_signifiers,
        record.analysis.empty_signifier_candidates,
        record.analysis.formations,
        record.analysis.imaginaries,
        record.analysis.frontier,
        record.analysis.affects,
    ]
    for group in object_groups:
        for obj in group:
            object_id = getattr(obj, "object_id", None) or getattr(obj, "entity_id", None)
            if object_id is None:
                object_id = getattr(obj, "topic_id", None) or getattr(obj, "label", None)
            if object_id is None:
                continue
            label = getattr(obj, "label", None) or getattr(obj, "name", None) or str(object_id)
            kind = getattr(obj, "kind", None) or getattr(obj, "entity_type", None) or "topic"
            review_status = getattr(obj, "review_status", "PROVISIONAL")
            provenance_id = getattr(obj, "provenance_id", "")
            nodes.append(
                {
                    "id": str(object_id),
                    "type": str(kind),
                    "label": str(label),
                    "review_status": str(review_status),
                    "provenance_id": str(provenance_id),
                }
            )
            edges.append(
                {
                    "id": f"candidate-in:{object_id}",
                    "source": record.source_url,
                    "target": str(object_id),
                    "type": "CANDIDATE_IN",
                }
            )
            for evidence_id in getattr(obj, "evidence_ids", []):
                edges.append(
                    {
                        "id": f"evidence-for:{evidence_id}:{object_id}",
                        "source": str(evidence_id),
                        "target": str(object_id),
                        "type": "EVIDENCE_FOR",
                    }
                )

    relations = (
        list(record.analysis.relations)
        + list(record.analysis.antagonisms)
        + list(record.analysis.actor_entity_relations)
    )
    for relation in relations:
        edges.append(
            {
                "id": relation.relation_id,
                "source": relation.source_ref,
                "target": relation.target_ref,
                "type": relation.relation_type.upper(),
                "review_status": relation.review_status,
                "provenance_id": relation.provenance_id,
                "evidence_ids": list(relation.evidence_ids),
            }
        )
        # Relation evidence remains attached to the relation edge via
        # `evidence_ids`. Do not emit an edge to `relation.relation_id`:
        # relation IDs identify edges, not nodes, and using them as endpoints
        # creates dangling references that GraphML/GEXF silently materialize as
        # phantom nodes during export.
    for chain in record.analysis.equivalence_chains + record.analysis.difference_chains:
        relation_type = "EQUIVALENT_TO" if chain.chain_type == "equivalence" else "DIFFERENTIATED_FROM"
        for left, right in zip(chain.member_refs, chain.member_refs[1:], strict=False):
            edges.append(
                {
                    "id": f"{chain.chain_id}:{left}:{right}",
                    "source": left,
                    "target": right,
                    "type": relation_type,
                    "chain_id": chain.chain_id,
                    "evidence_ids": list(chain.evidence_ids),
                    "review_status": chain.review_status,
                    "provenance_id": chain.provenance_id,
                }
            )

    return {
        "schema": "laclaugpt-discourse-graph-v1",
        "source_url": record.source_url,
        "nodes": nodes,
        "edges": edges,
    }


def run_canonical_pipeline(record: CanonicalRecord, *, provider, context: PipelineContext | None = None, codebook_entries: list[CodebookEntry] | None = None, preprocessor: Preprocessor | None = None, graph_sink: GraphSink | None = None, vector_sink: VectorSink | None = None, model: str = "auto", project_profile: str = "generic", prompt_version: str = "canonical-pipeline-v1", allow_cloud_fallback: bool | None = None) -> CanonicalRecord:
    ctx = context or PipelineContext()
    if project_profile.casefold() == "ai26":
        _validate_project_analysis_config(ctx)
    entries = codebook_entries or []
    record.analysis.started_at = record.analysis.started_at or datetime.now(UTC)
    preprocess_record(record, preprocessor=preprocessor)
    ensure_still_image_frames(record)
    plan = build_modality_plan(record)
    _append_stage(record, "modality_plan", {
        "created_at": datetime.now(UTC).isoformat(),
        **plan.audit(),
    })

    if plan.needs_frame_analysis:
        # Import the image-capable adapter lazily. Text/audio-only records never
        # need multimodal dependencies or a vision-capable provider wrapper.
        from .llm.multimodal import FrameAwareProvider

        frame_provider = FrameAwareProvider(
            provider,
            record.content.frames,
            record.content.media_references,
        )
        analyze_frames(
            record,
            provider=frame_provider,
            context=ctx,
            codebook_entries=entries,
            model=model,
            prompt_version=f"{prompt_version}:frame",
            project_profile=project_profile,
            allow_cloud_fallback=allow_cloud_fallback,
        )
        _append_stage(record, "multimodal_visibility", frame_provider.audit())
    else:
        _append_stage(record, "frame_analysis_skipped", {
            "created_at": datetime.now(UTC).isoformat(),
            "reason": "no_materialized_image_or_video_frames",
            "modality_plan": plan.audit(),
        })

    summary = summarize_record(record, provider=provider, context=ctx, codebook_entries=entries, model=model, prompt_version=f"{prompt_version}:summary", project_profile=project_profile, allow_cloud_fallback=allow_cloud_fallback)
    discourse = discourse_analysis(record, provider=provider, context=ctx, codebook_entries=entries, model=model, prompt_version=f"{prompt_version}:discourse", project_profile=project_profile, allow_cloud_fallback=allow_cloud_fallback) if _enabled(ctx, "laclau") or project_profile.casefold() != "ai26" else DiscourseProposal()
    postprocess_record(record, summary, discourse, ctx)
    record.legacy["multimodal_compatibility"] = legacy_multimodal_projection(record)
    # Phase 2 / experimental methods remain explicit opt-ins and never enter the
    # Phase 1 default path. They run only after the five canonical Phase 1 stages.
    if _enabled(ctx, "critical_ai", default=False):
        from .critical_ai import run_optional_critical_ai
        run_optional_critical_ai(
            record,
            provider=provider,
            context=ctx,
            codebook_entries=entries,
            model=model,
            allow_cloud_fallback=allow_cloud_fallback,
        )
    elif _enabled(ctx, "dna_statement_coding", default=False):
        from .dna_statement_coding import run_optional_dna_statement_coding
        run_optional_dna_statement_coding(
            record,
            provider=provider,
            context=ctx,
            codebook_entries=entries,
            model=model,
            allow_cloud_fallback=allow_cloud_fallback,
        )
    graph = build_discourse_graph(record)
    _append_stage(record, "discourse_graph", graph)
    if graph_sink:
        graph_sink.write_graph(record.source_url, graph)
    if vector_sink:
        vector_sink.upsert(record.source_url, record.human_readable.markdown or record.content.text, {"source_url": record.source_url, "project_profile": project_profile})
    return record
