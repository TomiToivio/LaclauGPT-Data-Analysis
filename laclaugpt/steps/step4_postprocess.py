"""Step 4 of 7 — postprocess.

Turn the free-text summary from step 3 into structured, queryable fields: topics,
entities and a sentiment split. This is what makes the corpus searchable and
comparable without re-reading every summary.

Descriptive only. Topics and entities are candidate structures, not
discourse-theoretical claims.

---------------------------------------------------------------------------
Purpose
---------------------------------------------------------------------------

Lift structured fields out of the summary:

  topics      what the record is about
  entities    people, organisations, products named in it
  sentiment   positive / neutral / negative spans

Out of scope: deciding what any of it means. A topic list is not a discourse, and
a negative sentiment is not an antagonism (AGENTS.md methodological boundary).

---------------------------------------------------------------------------
Legacy reference
---------------------------------------------------------------------------

LaclauGPT-Multimodal-Analysis / puhti_postprocess.py

  class Sentiment(BaseModel):  topics, entities, positive, neutral, negative
  analyze_responses()          read summary_analysis, asked the model for the
                               structured fields, de-duplicated each list with
                               dict.fromkeys while preserving order

Deliberate difference: the result is validated as a Pydantic model with an
explicit `extra` field, instead of being written straight into dataframe columns.

---------------------------------------------------------------------------
Inputs
---------------------------------------------------------------------------

  step_outputs.summary.output.summary     the text to structure
  record.text                              fallback when no summary exists
  record.language                          for downstream filtering

---------------------------------------------------------------------------
Outputs
---------------------------------------------------------------------------

  step_outputs.postprocess.output =
      Step4PostprocessOutput {
          topics:    [str]
          entities:  [str]
          sentiment: Sentiment{positive, neutral, negative}
          extra:     dict
      }

---------------------------------------------------------------------------
Model
---------------------------------------------------------------------------

A text LLM through the provider boundary, using the project's postprocess prompt.
Structured output must be validated against Step4PostprocessOutput before it is
written (AGENTS.md: never let unvalidated model output mutate the record). Use
the structured-output helper rather than parsing prose by hand.

---------------------------------------------------------------------------
Uncertainty
---------------------------------------------------------------------------

  no summary and no text    -> ABSTAINED, empty lists
  model returns unparseable output -> FAILED with the raw reply kept in notes, so
      the failure is inspectable rather than silent
  no sentiment spans found  -> empty lists are a valid result, not an error

---------------------------------------------------------------------------
Provenance
---------------------------------------------------------------------------

  model, prompt id/version, validation outcome, and a content hash of the input
  the fields were derived from — so a later re-summarisation can be detected as
  making these fields stale.

---------------------------------------------------------------------------
"""
from __future__ import annotations

from models.incoming import IncomingRecord
from models.steps import Step4PostprocessOutput

from steps import StepContext, StepResult, StepStatus


def run(record: IncomingRecord, *, context: StepContext) -> StepResult:
    """Extract structured fields from the summary.

    TO HAND-CODE (step 2 of issue #315). The body below is the shape, not the
    method.
    """
    summary = str((record.step_outputs.get("summary") or {}).get("output", {}).get("summary", ""))
    source_text = summary or record.text
    if not source_text.strip():
        return StepResult(
            status=StepStatus.ABSTAINED,
            output=Step4PostprocessOutput(),
            notes=["no summary or text to structure"],
        )

    # ---------------------------------------------------------------- TO CODE
    # Expected shape of the finished body, for readability:
    #
    #   prompt = load_prompt(context, "postprocess")
    #   payload = call_model_structured(source_text, Step4PostprocessOutput, context)
    #   payload.topics = dedupe(payload.topics)
    #   payload.entities = dedupe(payload.entities)
    #   return StepResult(output=payload)
    raise NotImplementedError(
        "step 4 (postprocess) is hand-coded by the researcher; see the module docstring"
    )
