"""Step 5 of 7 — Laclaudian discourse analysis.

The theoretical heart of the pipeline. Reads the record with the tools of Laclau
and Mouffe, in the reading developed by Palonen: how meanings are fixed,
contested and articulated, and how a collective subject is constituted against a
frontier.

This is interpretation, not computation, and it stays provisional until a human
researcher reviews it.

---------------------------------------------------------------------------
Purpose
---------------------------------------------------------------------------

Ask the discourse-theoretical questions of one record:

  chains of equivalence   which demands are articulated as equivalent
  frontier / antagonism   against what is the "we" constituted
  nodal points            meanings that appear fixed
  floating signifiers     meanings still contested
  empty-signifier candidates   signifiers carrying a heterogeneous chain
  affects                 the investment that holds an articulation together

Out of scope: counting. Frequency is not hegemony, semantic similarity is not
equivalence, and negative sentiment is not antagonism.

---------------------------------------------------------------------------
Legacy reference
---------------------------------------------------------------------------

LaclauGPT-Multimodal-Analysis / puhti_populism.py

  class PopulismElement(BaseModel):  populism_element, populism_affect
  class FormulaOfPopulism(BaseModel): populism_analysis, populism_us,
                                     populism_frontier
  get_formula_of_populism(country)   per-video analysis, wrote the populism table

Formula of populism (Palonen): a collective subject (Us) constituted against a
frontier, held together by affect.

Deliberate difference: the per-record analysis is separate from any corpus-level
aggregation. The legacy script computed a formula per country by reading every
video; here a single record yields a single record-level reading, and corpus
synthesis is a later, separate step (INV_HEGEMONY_CORPUS).

---------------------------------------------------------------------------
Inputs
---------------------------------------------------------------------------

  record.text                              the text being read
  record.source                            who said it, where, when
  step_outputs.summary.output.summary       the summary
  step_outputs.postprocess.output           topics/entities, as orientation only
  context.codebook                          the project's signifier concepts

---------------------------------------------------------------------------
Outputs
---------------------------------------------------------------------------

  step_outputs.discourse.output =
      Step5DiscourseOutput {
          populism_analysis:            str
          populism_us:                  [PopulismElement]
          populism_frontier:            [PopulismElement]
          signifiers:                   [str]
          nodal_points:                 [str]
          empty_signifier_candidates:   [str]
          abstained:                    bool
      }

---------------------------------------------------------------------------
Model
---------------------------------------------------------------------------

A text LLM through the provider boundary, using the project's discourse prompt
(see src/laclaugpt_data_analysis/prompts/laclau/ for the current versions). The
prompt must keep these four things distinguishable, or the model will attribute
one to another:

  source evidence        what this record actually says
  retrieved context      other records, explicitly not this one's evidence
  codebook concepts      the researcher's definitions
  memory candidates      previously established signifiers/actors

---------------------------------------------------------------------------
Uncertainty and theory invariants
---------------------------------------------------------------------------

These are not style preferences; they are the theory. Preserve them:

  INV_ABSTAIN        an empty reading is valid. A record with no evidence of a
                     frontier abstains rather than inventing one.
  INV_EVIDENCE       every theoretical claim keeps its source quote.
  INV_RELATIONAL     these are relations, not keyword categories.
  INV_ANTAGONISM     criticism or negative sentiment alone is not antagonism.
  INV_FLOAT_CORPUS   floating-signifier status needs competing fixations.
  INV_EMPTY_CHAIN    empty-signifier status needs a heterogeneous chain.
  INV_HEGEMONY_CORPUS  one record cannot establish hegemony.
  INV_POPULISM       populist=true requires evidenced Us and Frontier.
  INV_CONTEXT        quoted or reported claims are not the author's own position.
  INV_HUMAN_REVIEW   the output is provisional and human-rejectable.

---------------------------------------------------------------------------
Provenance
---------------------------------------------------------------------------

  model, prompt id/version, codebook version, and the evidence spans each claim
  rests on. A reader must be able to go from any claimed signifier or frontier
  element back to the passage that supports it.

---------------------------------------------------------------------------
"""
from __future__ import annotations

from models.incoming import IncomingRecord
from models.steps import Step5DiscourseOutput

from steps import StepContext, StepResult, StepStatus


def run(record: IncomingRecord, *, context: StepContext) -> StepResult:
    """Read one record with Laclau/Mouffe (Palonen) discourse theory.

    TO HAND-CODE (step 2 of issue #315). The body below is the shape, not the
    method.
    """
    summary = str((record.step_outputs.get("summary") or {}).get("output", {}).get("summary", ""))
    source_text = record.text or summary
    if not source_text.strip():
        return StepResult(
            status=StepStatus.ABSTAINED,
            output=Step5DiscourseOutput(abstained=True),
            notes=["no text to read; abstaining rather than inferring"],
        )

    # ---------------------------------------------------------------- TO CODE
    # Expected shape of the finished body, for readability:
    #
    #   prompt = load_prompt(context, "discourse")
    #   user = render(prompt, source=record.text, metadata=record.source,
    #                 summary=summary, codebook=context.codebook)
    #   reading = call_model_structured(user, Step5DiscourseOutput, context)
    #   # keep evidence and abstention intact; never promote a reading to a claim
    #   return StepResult(output=reading)
    raise NotImplementedError(
        "step 5 (discourse) is hand-coded by the researcher; see the module docstring"
    )
