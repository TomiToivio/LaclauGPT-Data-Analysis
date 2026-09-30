"""STEP 5 - Laclaudian discourse analysis.

Legacy reference: LaclauGPT-Multimodal-Analysis/puhti_populism.py
Phase 2 should preserve the current Laclau/Palonen method rather than copying
legacy binary-populism assumptions.
Human implementation belongs in this file.
"""

from pipeline_models import (
    HumanPipelineRecord,
    LaclauResult,
    PostprocessResult,
    SummaryResult,
)


def analyze_laclau(
    record: HumanPipelineRecord,
    summary: SummaryResult,
    descriptive: PostprocessResult,
) -> LaclauResult:
    """Interpret articulation, Us/frontier, demands, affects, and signifiers with evidence."""
    raise NotImplementedError("Tomi will hand-code Laclaudian analysis")
