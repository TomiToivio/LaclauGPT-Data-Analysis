"""STEP 2 - frame/image analysis, only when media is present.

Legacy reference: LaclauGPT-Multimodal-Analysis/puhti_frame.py
Human implementation belongs in this file.
"""

from pipeline_models import FrameObservation, HumanPipelineRecord


def analyze_frames(record: HumanPipelineRecord) -> list[FrameObservation]:
    """Describe visual evidence attached to the incoming post.

    Text-only records should simply return an empty list.
    """
    if not record.media:
        return []
    raise NotImplementedError("Tomi will hand-code multimodal frame analysis")
