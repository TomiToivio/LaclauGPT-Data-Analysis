"""Step 4: perform Phase 1 Laclauian discourse analysis.

This is the interpretive stage. It runs after the descriptive first pass so
observations about modalities remain distinct from discourse-theoretical claims.
The existing evidence, uncertainty, provenance, and abstention rules are reused
unchanged from the canonical implementation.
"""
from __future__ import annotations

from ..canonical import CanonicalRecord
from ..canonical_pipeline import (
    DiscourseProposal,
    PipelineContext,
    _enabled,
    discourse_analysis,
)
from ..codebooks import CodebookEntry


def run_laclau_analysis(
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
    """Run Laclau analysis when enabled; otherwise return an empty proposal."""
    if project_profile.casefold() == "ai26" and not _enabled(context, "laclau"):
        return DiscourseProposal()

    return discourse_analysis(
        record,
        provider=provider,
        context=context,
        codebook_entries=codebook_entries,
        model=model,
        prompt_version=prompt_version,
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )
