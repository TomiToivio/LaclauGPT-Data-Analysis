"""Step 5: validate, project, and prepare the analyzed record for persistence.

Postprocessing does not add a new interpretation. It converts the summary and
Laclau proposals into canonical fields, preserves uncertainty/provenance, builds
legacy-compatible projections, and leaves a record ready for storage/export.
"""
from __future__ import annotations

from ..canonical import CanonicalRecord
from ..canonical_pipeline import (
    DiscourseProposal,
    PipelineContext,
    SummaryResult,
    postprocess_record,
)
from ..modality_routing import legacy_multimodal_projection


def run_postprocess(
    record: CanonicalRecord,
    *,
    summary: SummaryResult,
    discourse: DiscourseProposal,
    context: PipelineContext,
) -> CanonicalRecord:
    """Finalize canonical Phase 1 fields and retain the useful legacy surface."""
    result = postprocess_record(record, summary, discourse, context)
    result.legacy["multimodal_compatibility"] = legacy_multimodal_projection(result)
    return result
