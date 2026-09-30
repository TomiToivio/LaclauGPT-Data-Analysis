"""STEP 1 - preprocess every incoming record.

Legacy reference: LaclauGPT-Multimodal-Analysis/puhti_preprocess.py
Human implementation belongs in this file.
"""

from pipeline_models import HumanPipelineRecord


def preprocess(record: HumanPipelineRecord) -> HumanPipelineRecord:
    """Normalize usable text/media/metadata while preserving source_url.

    TODO(Tomi):
    - port only the useful, readable legacy preprocessing behaviour;
    - normalize text and media references;
    - preserve provenance and original evidence;
    - do not perform discourse interpretation here.
    """
    raise NotImplementedError("Tomi will hand-code Phase 2 preprocessing")
