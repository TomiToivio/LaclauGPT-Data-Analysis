"""Opt-in text-only Phase 1 runtime layered beside the stable Phase 0 pipeline."""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .analysis_context import codebook_context
from .canonical import CanonicalRecord, SCHEMA_VERSION
from .canonical_pipeline import (
    PipelineContext,
    analyze_frames,
    discourse_analysis,
    postprocess_record,
    summarize_record,
)
from .codebooks import CodebookEntry
from .interchange import from_mongo_document, from_phase0_mongo_document
from .memory.normalization import apply_accepted_memory
from .memory.sqlite import SQLiteMemory
from .phase1_shadow import preprocess_shadow_record


PHASE1_NAMESPACE = "phase1"
PHASE1_RUNTIME_VERSION = "phase1-text-v1"


@dataclass(frozen=True)
class Phase1TextConfig:
    enabled: bool = False
    discourse_enabled: bool = False
    ep24_frame_analysis_enabled: bool = False
    codebook_context_enabled: bool = False
    codebook_context_limit: int = 12
    analytical_memory_enabled: bool = False
    model: str = "auto"
    prompt_version: str = "phase1-text-v1"
    project_profile: str = "ai26"
    allow_cloud_fallback: bool = False

    @classmethod
    def from_env(cls) -> "Phase1TextConfig":
        def flag(name: str, default: bool = False) -> bool:
            value = os.getenv(name)
            if value is None:
                return default
            return value.strip().casefold() in {"1", "true", "yes", "on"}

        try:
            codebook_context_limit = max(0, int(os.getenv("LACLAUGPT_PHASE1_CODEBOOK_CONTEXT_LIMIT", "12")))
        except ValueError:
            codebook_context_limit = 12

        return cls(
            enabled=flag("LACLAUGPT_PHASE1_ENABLED", False),
            discourse_enabled=flag("LACLAUGPT_PHASE1_DISCOURSE_ENABLED", False),
            ep24_frame_analysis_enabled=flag("LACLAUGPT_PHASE1_EP24_FRAME_ANALYSIS_ENABLED", False),
            codebook_context_enabled=flag("LACLAUGPT_PHASE1_CODEBOOK_CONTEXT_ENABLED", False),
            codebook_context_limit=codebook_context_limit,
            analytical_memory_enabled=flag("LACLAUGPT_PHASE1_ANALYTICAL_MEMORY_ENABLED", False),
            model=os.getenv("LACLAUGPT_PHASE1_MODEL", "auto"),
            prompt_version=os.getenv("LACLAUGPT_PHASE1_PROMPT_VERSION", "phase1-text-v1"),
            project_profile=os.getenv("LACLAUGPT_PHASE1_PROJECT_PROFILE", "ai26"),
            allow_cloud_fallback=flag("LACLAUGPT_PHASE1_ALLOW_CLOUD_FALLBACK", False),
        )


def phase1_context(base: PipelineContext | None = None) -> PipelineContext:
    """Return a Phase-1-only context with experimental Phase 2 methods disabled."""
    source = base or PipelineContext()
    config = dict(source.project_config)
    analysis = dict(config.get("analysis") or {})
    analysis.update(
        {
            "laclau": True,
            "critical_ai": False,
            "dna_statement_coding": False,
        }
    )
    config["analysis"] = analysis
    config["analysis_phase"] = 1
    return source.model_copy(update={"project_config": config})


def select_relevant_codebook_entries(
    record: CanonicalRecord, entries: list[CodebookEntry], *, limit: int = 12
) -> list[CodebookEntry]:
    """Select codebook concepts explicitly named in the current source text.

    This intentionally performs no retrieval, memory lookup, or model inference.
    A concept is included only when its label or an alias occurs as a whole phrase
    in the current record, making the optional context independently reversible.
    """
    if limit <= 0:
        return []
    source = " ".join(
        value for value in (record.title, record.content.text) if value
    )
    selected: list[CodebookEntry] = []
    for entry in entries:
        terms = (entry.label, *entry.aliases)
        if any(
            term.strip() and re.search(r"(?<!\w)" + re.escape(term.strip()) + r"(?!\w)", source, re.IGNORECASE)
            for term in terms
        ):
            selected.append(entry)
            if len(selected) >= limit:
                break
    return selected


def phase1_codebook_context(
    context: PipelineContext, entries: list[CodebookEntry], *, limit: int
) -> PipelineContext:
    """Add auditable project-codebook context without using memory or RAG slots."""
    fragment = codebook_context(entries, limit=limit)
    source_context = "\n\n".join(part for part in (context.source_context, fragment.text) if part)
    provenance = {key: list(values) for key, values in context.provenance.items()}
    provenance.setdefault("source", []).append(fragment.provenance_token())
    return context.model_copy(update={
        "source_context": source_context,
        "provenance": provenance,
        "codebook_revision": context.codebook_revision or fragment.sha256,
    })


def resolve_analytical_memory(
    memory: SQLiteMemory, candidates: list[tuple[str, str]]
) -> list[str]:
    """Return pre-accepted stable IDs without creating or promoting candidates."""
    resolved: list[str] = []
    seen: set[str] = set()
    for kind, raw in candidates:
        result = memory.resolve_accepted(raw, kind)
        if result.decision == "EXISTING" and result.obj_id not in seen:
            resolved.append(result.obj_id)
            seen.add(result.obj_id)
    return resolved


def _record_memory_resolution(
    record: CanonicalRecord, memory: SQLiteMemory, candidates: list[tuple[str, str]]
) -> None:
    refs = resolve_analytical_memory(memory, candidates)
    record.analysis.memory_refs = list(dict.fromkeys([*record.analysis.memory_refs, *refs]))
    apply_accepted_memory(record, memory)
    record.intermediate.stage_outputs["phase1_analytical_memory"] = [{
        "enabled": True,
        "role": "continuity_normalization_not_evidence",
        "resolution": "deterministic_accepted_alias_only",
        "candidate_count": len(candidates),
        "resolved_ids": refs,
        "created_or_promoted": False,
    }]


def run_phase1_text_record(
    document: Mapping[str, Any],
    *,
    provider,
    config: Phase1TextConfig | None = None,
    context: PipelineContext | None = None,
    codebook_entries: list[CodebookEntry] | None = None,
    analytical_memory: SQLiteMemory | None = None,
) -> CanonicalRecord:
    """Run the text-only Phase 1 slice without changing the Phase 0 source document.

    The caller supplies a copied Mongo-shaped mapping. Phase 0 output remains under
    record.legacy["phase0"]; new canonical analysis is written only to the returned
    canonical record.
    """
    cfg = config or Phase1TextConfig.from_env()
    record = from_phase0_mongo_document(document)
    if not cfg.enabled:
        return record

    preprocess_shadow_record(record)
    ctx = phase1_context(context)
    entries = codebook_entries or []
    selected_entries: list[CodebookEntry] = []
    if cfg.codebook_context_enabled:
        selected_entries = select_relevant_codebook_entries(
            record, entries, limit=cfg.codebook_context_limit
        )
        ctx = phase1_codebook_context(
            ctx, selected_entries, limit=cfg.codebook_context_limit
        )
        record.intermediate.stage_outputs["phase1_codebook_context"] = [{
            "enabled": True,
            "selection_method": "current_source_label_or_alias_match",
            "evidence_role": "researcher_context",
            "selected_entries": [
                {"kind": entry.kind, "label": entry.label} for entry in selected_entries
            ],
            "codebook_context_sha256": ctx.codebook_revision,
        }]

    # Phase 1 remains text-first by default. Frame analysis is an explicit
    # EP24-only opt-in; it never activates AI26 multimodal dependencies.
    if cfg.ep24_frame_analysis_enabled and cfg.project_profile.casefold() == "ep24":
        analyze_frames(
            record, provider=provider, context=ctx, codebook_entries=[],
            model=cfg.model, prompt_version=f"{cfg.prompt_version}:frame",
            project_profile="ep24", allow_cloud_fallback=cfg.allow_cloud_fallback,
        )

    summary = summarize_record(
        record,
        provider=provider,
        context=ctx,
        codebook_entries=[],
        model=cfg.model,
        prompt_version=f"{cfg.prompt_version}:summary",
        project_profile=cfg.project_profile,
        allow_cloud_fallback=cfg.allow_cloud_fallback,
    )
    record.analysis.summary = summary.summary or None
    record.analysis.status = "phase1-summary-only"

    summary_memory_candidates = (
        [("entity", value) for value in summary.entities]
        + [("topic", value) for value in summary.topics]
        + [("actor", value) for event in summary.event_candidates for value in event.actors]
    )
    if not cfg.discourse_enabled:
        if cfg.analytical_memory_enabled and analytical_memory is not None:
            _record_memory_resolution(record, analytical_memory, summary_memory_candidates)
        return record

    discourse = discourse_analysis(
        record,
        provider=provider,
        context=ctx,
        codebook_entries=[],
        model=cfg.model,
        prompt_version=f"{cfg.prompt_version}:discourse",
        project_profile=cfg.project_profile,
        allow_cloud_fallback=cfg.allow_cloud_fallback,
    )
    result = postprocess_record(record, summary, discourse, ctx)
    if cfg.analytical_memory_enabled and analytical_memory is not None:
        signifiers = [item.label for item in result.analysis.signifiers]
        _record_memory_resolution(
            result, analytical_memory, summary_memory_candidates + [("signifier", value) for value in signifiers]
        )
    return result


def phase1_persistence_payload(record: CanonicalRecord) -> dict[str, Any]:
    """Create the single namespaced Mongo value used by Phase 1 persistence."""
    return {
        "runtime_version": PHASE1_RUNTIME_VERSION,
        "schema_version": SCHEMA_VERSION,
        "source_url": record.source_url,
        "status": record.analysis.status,
        "canonical_record": record.canonical_dict(),
    }


def persist_phase1_record(
    collection: Any,
    source_document: Mapping[str, Any],
    record: CanonicalRecord,
) -> Any:
    """Idempotently $set a Phase 1 namespace without overwriting Phase 0 fields.

    collection only needs the pymongo-compatible update_one method, keeping the helper
    unit-testable with a fake collection and avoiding a hard pymongo dependency.
    """
    if source_document.get("_id") is not None:
        identity = {"_id": source_document["_id"]}
    elif source_document.get("document_id"):
        identity = {"document_id": source_document["document_id"]}
    elif source_document.get("source_url"):
        identity = {"source_url": source_document["source_url"]}
    else:
        raise ValueError("cannot persist Phase 1 record without stable Phase 0 identity")
    return collection.update_one(
        identity,
        {"$set": {PHASE1_NAMESPACE: phase1_persistence_payload(record)}},
        upsert=False,
    )

def load_persisted_phase1_record(source_document: Mapping[str, Any]) -> CanonicalRecord | None:
    """Reload a previously persisted canonical Phase 1 record without recomputation."""
    namespace = source_document.get(PHASE1_NAMESPACE)
    if not isinstance(namespace, Mapping):
        return None
    payload = namespace.get("canonical_record")
    if not isinstance(payload, Mapping):
        return None
    return from_mongo_document(payload)


def persist_phase1_failure(
    collection: Any,
    source_document: Mapping[str, Any],
    *,
    stage: str,
    error: Exception,
) -> Any:
    """Persist an isolated Phase 1 stage failure without touching Phase 0 fields."""
    normalized_stage = stage.strip()
    if not normalized_stage or any(char in normalized_stage for char in ".$"):
        raise ValueError("stage must be a non-empty Mongo-safe field name")

    if source_document.get("_id") is not None:
        identity = {"_id": source_document["_id"]}
    elif source_document.get("document_id"):
        identity = {"document_id": source_document["document_id"]}
    elif source_document.get("source_url"):
        identity = {"source_url": source_document["source_url"]}
    else:
        raise ValueError("cannot persist Phase 1 failure without stable Phase 0 identity")

    metadata = source_document.get("metadata")
    metadata_source_url = metadata.get("source_url") if isinstance(metadata, Mapping) else None
    source_url = str(source_document.get("source_url") or metadata_source_url or "")
    prefix = f"{PHASE1_NAMESPACE}.failures.{normalized_stage}"
    return collection.update_one(
        identity,
        {
            "$set": {
                f"{PHASE1_NAMESPACE}.runtime_version": PHASE1_RUNTIME_VERSION,
                f"{PHASE1_NAMESPACE}.schema_version": SCHEMA_VERSION,
                f"{PHASE1_NAMESPACE}.source_url": source_url,
                f"{PHASE1_NAMESPACE}.status": "failed",
                f"{prefix}.last_error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            },
            "$inc": {f"{prefix}.attempts": 1},
        },
        upsert=False,
    )

