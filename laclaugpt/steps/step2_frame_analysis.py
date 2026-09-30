"""Step 2 of 7 — frame analysis.

Read the record's images and sampled video frames: what is shown, what text is on
screen, what the image itself communicates. This is the visual counterpart to the
text reading the later steps do.

Optional by nature. A record with no images or frames skips this step cleanly.

---------------------------------------------------------------------------
Purpose
---------------------------------------------------------------------------

Produce one visual reading per image or sampled frame:

  what is depicted        people, objects, setting, actions
  on-screen text          captions, overlays, signage
  social-semiotic markers gesture, framing, colour, composition

Out of scope: interpreting what the image means politically or discursively.
That belongs to step 5. This step describes what is visible.

---------------------------------------------------------------------------
Legacy reference
---------------------------------------------------------------------------

LaclauGPT-Multimodal-Analysis / puhti_frame.py

  get_analysis(frame_file)   one Llama vision call per frame, image sent as
                             base64; wrote frame_analysis_1..6

Deliberate difference: the reading is attached to the frame it describes rather
than being positional, and the model is configurable instead of hard-coded to
`llama3.2-vision:11b`.

---------------------------------------------------------------------------
Inputs
---------------------------------------------------------------------------

  record.image_items            images to read directly
  step_outputs.preprocess       frames + their OCR text, when step 1 produced them
  record.text                   for orientation only, not as the thing being read
  context.codebook              optional retrieval hints

---------------------------------------------------------------------------
Outputs
---------------------------------------------------------------------------

  step_outputs.frame_analysis.output =
      Step2FrameOutput {
          readings:         [FrameReading{frame_id, analysis, abstained,
                                          confidence, notes}]
          skipped_no_media: bool
      }

---------------------------------------------------------------------------
Model
---------------------------------------------------------------------------

A vision-capable LLM through the provider boundary in
src/laclaugpt_data_analysis/llm/. The prompt comes from the project's prompt
directory, so a project can tune its own visual reading without changing this
step. Record the model and prompt version in provenance.

---------------------------------------------------------------------------
Uncertainty
---------------------------------------------------------------------------

  no media                  -> StepStatus.SKIPPED, skipped_no_media=True
  unreadable / blank frame  -> FrameReading(abstained=True), never a guess
  low confidence            -> set confidence, and abstain if too low to read

---------------------------------------------------------------------------
Provenance
---------------------------------------------------------------------------

Per reading: frame id, the model that produced it, the prompt id/version, and
the confidence. Like every model-produced field these are provisional until a
human reviews them (INV_HUMAN_REVIEW).

---------------------------------------------------------------------------
"""
from __future__ import annotations

from models.incoming import IncomingRecord
from models.steps import Step2FrameOutput

from steps import StepContext, StepResult, StepStatus


def run(record: IncomingRecord, *, context: StepContext) -> StepResult:
    """Read the visual material on one record.

    TO HAND-CODE (step 2 of issue #315). The body below is the shape, not the
    method.
    """
    has_frames = bool(record.image_items) or bool(
        (record.step_outputs.get("preprocess") or {}).get("output", {}).get("frames")
    )
    if not has_frames:
        return StepResult(
            status=StepStatus.SKIPPED,
            output=Step2FrameOutput(skipped_no_media=True),
            notes=["record has no images or frames; frame analysis not applicable"],
        )

    # ---------------------------------------------------------------- TO CODE
    # Expected shape of the finished body, for readability:
    #
    #   readings = []
    #   for image in record.image_items:
    #       readings.append(read_frame(image, context))
    #   for frame in preprocess_frames(record):
    #       readings.append(read_frame(frame, context))
    #   return StepResult(output=Step2FrameOutput(readings=readings))
    raise NotImplementedError(
        "step 2 (frame analysis) is hand-coded by the researcher; see the module docstring"
    )
