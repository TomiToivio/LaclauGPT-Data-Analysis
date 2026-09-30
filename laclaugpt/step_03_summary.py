"""STEP 3 - one summary for every record, text-only or multimodal.

Legacy reference: LaclauGPT-Multimodal-Analysis/puhti_summary.py
Human implementation belongs in this file.
"""

from pipeline_models import FrameObservation, HumanPipelineRecord, SummaryResult


def summarize(
    record: HumanPipelineRecord, frames: list[FrameObservation]
) -> SummaryResult:
    """Combine source text, metadata, and any visual observations into evidence-aware summary."""
    raise NotImplementedError("Tomi will hand-code multimodal summary")
