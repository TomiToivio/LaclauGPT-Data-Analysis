"""Step 3 of 7 — summary.

Summarise the whole record: the source metadata, its text, the transcript, and the
frame readings from step 2. One summary per record, whether the record is
text-only or multimodal.

This is the step that turns a pile of extracted material into a single readable
account, which the later steps then work from.

---------------------------------------------------------------------------
Purpose
---------------------------------------------------------------------------

Produce one summary of the record as a whole: what is being communicated, by
whom, about what. Both text-only and multimodal records go through this step;
the difference is only which inputs are present.

Out of scope: structured extraction (step 4) and discourse theory (step 5). The
summary is prose, not a verdict.

---------------------------------------------------------------------------
Legacy reference
---------------------------------------------------------------------------

LaclauGPT-Multimodal-Analysis / puhti_summary.py

  get_llama_summary_user_prompt(metadata, transcript, frame_analysis)
      assembled metadata + transcript + frame readings into one prompt
  get_llama_summary_system_prompt()
      the "social-semiotic multimodal pre-analysis" system instruction
  -> wrote the single column summary_analysis

Deliberate difference: the prompt lives in the project's prompt directory rather
than inline in the script, so a project can version its own wording.

---------------------------------------------------------------------------
Inputs
---------------------------------------------------------------------------

  record.source         metadata: platform, author, date, language
  record.text           the post's own text
  record.title          where present
  step_outputs.preprocess.output.transcript      audio transcript
  step_outputs.frame_analysis.output.readings    visual readings
  context.codebook      optional retrieval hints

A text-only record supplies only the first three; that is a complete input set.

---------------------------------------------------------------------------
Outputs
---------------------------------------------------------------------------

  step_outputs.summary.output =
      Step3SummaryOutput {summary: str, abstained: bool, notes: [str]}

---------------------------------------------------------------------------
Model
---------------------------------------------------------------------------

A text LLM through the provider boundary. The prompt is the project's summary
prompt; its id and version are recorded in provenance. A multimodal summary may
in future use a vision model directly, in which case this step's provenance must
record which model actually read the images.

---------------------------------------------------------------------------
Uncertainty
---------------------------------------------------------------------------

  no usable text and no readable media -> StepStatus.ABSTAINED with an empty
      summary; an empty summary is a valid result (INV_ABSTAIN), not a failure
  partial input (for example transcript only, no frames) -> summarise what is
      present and say so in notes, rather than inventing the missing modality

---------------------------------------------------------------------------
Provenance
---------------------------------------------------------------------------

  model, prompt id/version, and which inputs were actually available. Recording
  the input set matters: a summary from text alone is not comparable to one that
  also saw the video frames, and a reader needs to know which they are reading.

---------------------------------------------------------------------------
"""
from __future__ import annotations

from models.incoming import IncomingRecord
from models.steps import Step3SummaryOutput

from steps import StepContext, StepResult, StepStatus


def run(record: IncomingRecord, *, context: StepContext) -> StepResult:
    """Summarise one record, text-only or multimodal.

    TO HAND-CODE (step 2 of issue #315). The body below is the shape, not the
    method.
    """
    has_input = bool(record.text.strip()) or bool(record.media) or bool(record.step_outputs)
    if not has_input:
        return StepResult(
            status=StepStatus.ABSTAINED,
            output=Step3SummaryOutput(abstained=True, notes=["no analysable input"]),
            notes=["nothing to summarise"],
        )

    # ---------------------------------------------------------------- TO CODE
    # Expected shape of the finished body, for readability:
    #
    #   prompt = load_prompt(context, "summary")
    #   user = render(prompt, metadata=record.source, text=record.text,
    #                 transcript=transcript_of(record),
    #                 frames=frame_readings_of(record))
    #   summary = call_model(user, context)
    #   return StepResult(output=Step3SummaryOutput(summary=summary))
    raise NotImplementedError(
        "step 3 (summary) is hand-coded by the researcher; see the module docstring"
    )
