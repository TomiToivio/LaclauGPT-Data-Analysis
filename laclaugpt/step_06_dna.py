"""STEP 6 - Discourse Network Analysis.

Phase 2 addition. The bridge is document/actor discourse analysis -> explicit,
evidence-bearing claims and relations suitable for Philip Leifeld-style DNA.
Human implementation belongs in this file.
"""

from pipeline_models import DNAResult, HumanPipelineRecord, LaclauResult


def analyze_dna(record: HumanPipelineRecord, laclau: LaclauResult) -> DNAResult:
    """Project validated discourse claims into an explicit discourse network."""
    raise NotImplementedError("Tomi will hand-code Discourse Network Analysis")
