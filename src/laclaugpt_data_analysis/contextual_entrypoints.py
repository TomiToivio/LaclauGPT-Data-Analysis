"""Production CLI adapters that preserve existing orchestration but unify scientific context."""
from __future__ import annotations

from typing import Any

from .canonical import CanonicalRecord
from .canonical_pipeline import PipelineContext
from .config import load_settings
from .contextual_pipeline import run_contextual_canonical_pipeline
from .critical_ai import run_optional_critical_ai
from .production_context import (
    production_context_policy,
    production_retrieval_backend,
    production_summary_repository,
)


def _contextual_run(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext | None = None,
    codebook_entries=None,
    preprocessor=None,
    graph_sink=None,
    vector_sink=None,
    model: str = "auto",
    project_profile: str = "generic",
    prompt_version: str = "canonical-v1",
    allow_cloud_fallback: bool | None = None,
    **_: Any,
) -> CanonicalRecord:
    """Signature-compatible replacement for the old production pipeline call."""
    settings = load_settings()
    policy = production_context_policy(settings, project_profile=project_profile)
    summary_repository = production_summary_repository(settings)
    retrieval_backend = production_retrieval_backend(settings)
    entries = list(codebook_entries or [])
    result = run_contextual_canonical_pipeline(
        record,
        provider=provider,
        project_id=settings.project_id,
        codebook_entries=entries,
        policy=policy,
        summary_repository=summary_repository,
        retrieval_backend=retrieval_backend,
        preprocessor=preprocessor,
        graph_sink=graph_sink,
        vector_sink=vector_sink,
        model=model,
        project_profile=project_profile,
        prompt_version=prompt_version,
        allow_cloud_fallback=allow_cloud_fallback,
    )
    if context is not None:
        if context.provenance:
            result.intermediate.stage_outputs.setdefault("caller_context_provenance", []).append(
                context.provenance
            )
        # The unified-context path must preserve the same optional-stage semantics
        # as the canonical runner. The frozen worker config lives on caller context.
        run_optional_critical_ai(
            result,
            provider=provider,
            context=context,
            codebook_entries=entries,
            model=model,
            allow_cloud_fallback=allow_cloud_fallback,
        )
    return result


def reprocessing_main(argv: list[str] | None = None) -> int:
    """Keep the existing reprocessing engine, but route its model work through unified context."""
    from . import reprocessing as legacy

    legacy.run_canonical_pipeline = _contextual_run
    return legacy.main(argv)


def worker_main(argv: list[str] | None = None) -> int:
    """Keep Redis/Mongo task semantics, but route analysis through unified context."""
    from . import distributed_worker as legacy

    legacy.run_canonical_pipeline = _contextual_run
    return legacy.main(argv)
