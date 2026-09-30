"""Step 3: create the descriptive first-pass summary.

This is intentionally before Laclauian interpretation. It integrates whatever
evidence is available in the canonical record: post text/caption, metadata,
transcript/ASR, OCR, and frame analyses. Text-only records use the same stage
without pretending that missing visual or audio evidence exists.
"""
from __future__ import annotations

from ..canonical import CanonicalRecord
from ..canonical_pipeline import PipelineContext, SummaryResult, summarize_record
from ..codebooks import CodebookEntry


def run_summary(
    record: CanonicalRecord,
    *,
    provider,
    context: PipelineContext,
    codebook_entries: list[CodebookEntry],
    model: str,
    prompt_version: str,
    project_profile: str,
    allow_cloud_fallback: bool | None,
) -> SummaryResult:
    """Produce the evidence-preserving social-semiotic pre-analysis."""
    return summarize_record(
        record,
        provider=provider,
        context=context,
        codebook_entries=codebook_entries,
        model=model,
        prompt_version=prompt_version,
        project_profile=project_profile,
        allow_cloud_fallback=allow_cloud_fallback,
    )
