"""Phase 2 / experimental methods, kept out of the orchestrator (#303).

The runner sequences the five canonical Phase 1 stages. Which *experimental* method may follow them is a
configuration question, and it lives here so the runner can stay readable: it calls
:func:`run_optional_methods` and does not carry a branch per method.

Nothing here runs by default. Phase 2 is an explicit opt-in, and the dispatch is an ``elif`` chain because
two experimental codings on one record would make the stored result ambiguous about which one produced it.
"""
from __future__ import annotations

from ..canonical import CanonicalRecord
from ..codebooks import CodebookEntry
from .shared import PipelineContext, enabled


def run_optional_methods(
    record: CanonicalRecord,
    *,
    ctx: PipelineContext,
    provider,
    codebook_entries: list[CodebookEntry],
    model: str,
    allow_cloud_fallback: bool | None,
) -> str:
    """Run the configured Phase 2 method, if any. Returns its name, or "" when nothing ran.

    The imports are local on purpose: an opt-in module that is not installed (or is being refactored) must
    not be able to break the Phase 1 path that never calls it.
    """
    if enabled(ctx, "critical_ai", default=False):
        from ..critical_ai import run_optional_critical_ai

        run_optional_critical_ai(
            record,
            provider=provider,
            context=ctx,
            codebook_entries=codebook_entries,
            model=model,
            allow_cloud_fallback=allow_cloud_fallback,
        )
        return "critical_ai"
    if enabled(ctx, "dna_statement_coding", default=False):
        from ..dna_statement_coding import run_optional_dna_statement_coding

        run_optional_dna_statement_coding(
            record,
            provider=provider,
            context=ctx,
            codebook_entries=codebook_entries,
            model=model,
            allow_cloud_fallback=allow_cloud_fallback,
        )
        return "dna_statement_coding"
    return ""
