"""Step 6 of 7 — Discourse Network Analysis (DNA).

Turn the discourse reading from step 5 into actor-concept statements: who says
what, and with what agreement. This is the layer that makes the corpus buildable
into a network.

New in Phase 2. The legacy pipeline has no network layers.

---------------------------------------------------------------------------
Purpose
---------------------------------------------------------------------------

Extract explicit statements of the form:

  actor  --  concept  --  agreement

"actor A supports concept C", "actor B rejects concept C". Statements are what
the network projections are built from, so this step is the bridge between the
discourse reading and any network claim.

Out of scope: building the network itself (step 7) and any corpus-level
interpretation.

---------------------------------------------------------------------------
Legacy reference
---------------------------------------------------------------------------

None. The legacy pipeline stops at the discourse reading. The semantics below
follow the verified model from issue #307, which was checked against
leifeld-lab/dna's own exporter and rDNA's tests:

  * agreement is genuinely binary: support = true, reject = false;
  * uncoded / ambiguous agreement stays None. It must never be coerced to
    support, and absence means no recorded position;
  * a statement needs an actor and a concept; an actor-less row is not a
    statement (this is what broke the sample.dna import before #307).

---------------------------------------------------------------------------
Inputs
---------------------------------------------------------------------------

  step_outputs.discourse.output   signifiers, nodal points, the Us/Frontier
                                  elements, and the record's own text
  record.source                   the default actor when the record is
                                  attributed to its author
  record.text                     for the evidence span

---------------------------------------------------------------------------
Outputs
---------------------------------------------------------------------------

  step_outputs.dna.output =
      Step6DnaOutput {
          statements: [DnaStatement{statement_id, actor_id, actor_name,
                                    concept_id, concept_label, agreement,
                                    agreement_status, evidence_text}]
          abstained:  bool
      }

---------------------------------------------------------------------------
Model
---------------------------------------------------------------------------

A text LLM through the provider boundary, using the project's DNA prompt (see
src/laclaugpt_data_analysis/prompts/dna/). The reply must be validated against
Step6DnaOutput before it is written.

If the step instead reads a DNA project written by hand, use the native adapter
in src/laclaugpt_data_analysis/interoperability/dna/ rather than re-parsing the
SQLite file here — it already handles the statement-type scoping and the
agreement domain correctly.

---------------------------------------------------------------------------
Uncertainty
---------------------------------------------------------------------------

  no coder position identifiable   -> agreement=None, agreement_status="abstain"
  quoted or reported claim         -> do not attribute it as the author's own
                                      position (INV_CONTEXT)
  no statements found              -> empty list and ABSTAINED, not a failure

An abstained statement is still a valid statement; only its agreement is unset.

---------------------------------------------------------------------------
Provenance
---------------------------------------------------------------------------

Per statement: the evidence text it came from, and the model/prompt that
produced the coding. Statements are also the input to the RDF export, so their
ids must stay stable for a given record.

---------------------------------------------------------------------------
"""
from __future__ import annotations

from models.incoming import IncomingRecord
from models.steps import Step6DnaOutput

from steps import StepContext, StepResult, StepStatus


def run(record: IncomingRecord, *, context: StepContext) -> StepResult:
    """Extract actor-concept statements from the discourse reading.

    TO HAND-CODE (step 2 of issue #315). The body below is the shape, not the
    method.
    """
    discourse = (record.step_outputs.get("discourse") or {}).get("output") or {}
    source_text = record.text or str(discourse.get("populism_analysis", ""))
    if not source_text.strip():
        return StepResult(
            status=StepStatus.ABSTAINED,
            output=Step6DnaOutput(abstained=True),
            notes=["no text to code into statements"],
        )

    # ---------------------------------------------------------------- TO CODE
    # Expected shape of the finished body, for readability:
    #
    #   prompt = load_prompt(context, "dna")
    #   user = render(prompt, source=record.text, discourse=discourse)
    #   coded = call_model_structured(user, Step6DnaOutput, context)
    #   for statement in coded.statements:
    #       statement.statement_id = stable_id(record.source_url, statement)
    #       if statement.agreement is None:
    #           statement.agreement_status = "abstain"   # never coerce to support
    #   return StepResult(output=coded)
    raise NotImplementedError(
        "step 6 (DNA) is hand-coded by the researcher; see the module docstring"
    )
