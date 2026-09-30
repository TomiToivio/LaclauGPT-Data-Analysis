"""STEP 4 - descriptive postprocessing.

Legacy reference: LaclauGPT-Multimodal-Analysis/puhti_postprocess.py
Human implementation belongs in this file.
"""

from pipeline_models import HumanPipelineRecord, PostprocessResult, SummaryResult


def postprocess(
    record: HumanPipelineRecord, summary: SummaryResult
) -> PostprocessResult:
    """Extract descriptive entities, topics, and affects without theory-facing inference."""
    raise NotImplementedError("Tomi will hand-code postprocessing")
