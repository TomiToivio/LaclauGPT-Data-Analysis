"""STEP 7 - Social Network Analysis.

Phase 2 addition. Build social relations from source evidence/metadata and the
validated upstream analysis without treating semantic similarity as a social tie.
Human implementation belongs in this file.
"""

from pipeline_models import DNAResult, HumanPipelineRecord, SNAResult


def analyze_sna(
    record: HumanPipelineRecord, dna: DNAResult
) -> SNAResult:
    """Project evidence-backed actors/relations into the social-network layer."""
    raise NotImplementedError("Tomi will hand-code Social Network Analysis")
