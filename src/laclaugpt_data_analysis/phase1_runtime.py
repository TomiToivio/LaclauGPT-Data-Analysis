"""Opt-in text-only Phase 1 runtime layered beside the stable Phase 0 pipeline."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .canonical import CanonicalRecord, SCHEMA_VERSION
from .canonical_pipeline import (
    PipelineContext,
    discourse_analysis,
    postprocess_record,
    summarize_record,
)
from .codebooks import CodebookEntry
from .phase1_shadow import preprocess_shadow_record
from .interchange import from_phase0_mongo_document


PHASE1_NAMESPACE = "phase1"
PHASE1_RUNTIME_VERSION = "phase1-text-v1"


@dataclass(frozen=True)
class Phase1TextConfig:
    enabled: bool = False
    discourse_enabled: bool = False
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

        return cls(
            enabled=flag("LACLAUGPT_PHASE1_ENABLED", False),
            discourse_enabled=flag("LACLAUGPT_PHASE1_DISCOURSE_ENABLED", False),
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


def run_phase1_text_record(
    document: Mapping[str, Any],
    *,
    provider,
    config: Phase1TextConfig | None = None,
    context: PipelineContext | None = None,
    codebook_entries: list[CodebookEntry] | None = None,
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

    summary = summarize_record(
        record,
        provider=provider,
        context=ctx,
        codebook_entries=entries,
        model=cfg.model,
        prompt_version=f"{cfg.prompt_version}:summary",
        project_profile=cfg.project_profile,
        allow_cloud_fallback=cfg.allow_cloud_fallback,
    )
    record.analysis.summary = summary.summary or None
    record.analysis.status = "phase1-summary-only"

    if not cfg.discourse_enabled:
        return record

    discourse = discourse_analysis(
        record,
        provider=provider,
        context=ctx,
        codebook_entries=entries,
        model=cfg.model,
        prompt_version=f"{cfg.prompt_version}:discourse",
        project_profile=cfg.project_profile,
        allow_cloud_fallback=cfg.allow_cloud_fallback,
    )
    return postprocess_record(record, summary, discourse, ctx)


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
