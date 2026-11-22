"""#458 / D6: runs made under the verbatim instruction must be attributable as a new instrument."""

from laclaugpt_data_analysis.distributed_worker import AI26_PROMPT_VERSION


def test_the_evidence_instruction_change_bumped_the_prompt_version():
    """Pooling v1 and v2 runs would mix paraphrase-tolerant and verbatim coding."""
    assert AI26_PROMPT_VERSION == "canonical-pipeline-v2", (
        "the prompt changed what the model is asked for; without a version bump the "
        "corpus cannot separate old-instrument from new-instrument runs"
    )
