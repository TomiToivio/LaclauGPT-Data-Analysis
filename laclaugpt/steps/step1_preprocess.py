"""Step 1 of 7 — preprocess.

Extract what is not yet text: video frames, OCR text on those frames, an audio
transcript, and a translation when the language is not the analysis language.

This is the only step that touches media files directly, and it is the slowest,
so it runs first and records everything the later steps need so they never have
to open a media file again.

---------------------------------------------------------------------------
Purpose
---------------------------------------------------------------------------

Turn one incoming post into analysable text and frames:

  video  -> sampled frames on disk + transcript of the audio
  image  -> the image itself, no transcript
  text   -> nothing to do (report SKIPPED, not a failure)

Out of scope: interpreting any of it. This step extracts; it does not analyse.

---------------------------------------------------------------------------
Legacy reference
---------------------------------------------------------------------------

LaclauGPT-Multimodal-Analysis / puhti_preprocess.py

  get_keyframes()     sampled a frame every 30 s with OpenCV and saved it
  get_transcript()    Whisper transcript, then a Google translation
  analyze_videos()    wrote six fixed columns per video:
                          frames, ocr_1..ocr_6,
                          whisper_transcript, whisper_language, whisper_translated

Two deliberate differences from the legacy version:

  * frames are a list, not six fixed columns, so the sample count is not baked
    into the schema;
  * OCR text is attached to the frame it came from, instead of being positional.

The legacy script also created ./logs and ./database at import time. That is a
runtime-data boundary violation here (AGENTS.md): runtime files belong under
data/, reached through configuration, never created as a side effect of import.

---------------------------------------------------------------------------
Inputs
---------------------------------------------------------------------------

  record.media        the images and videos to extract from
  record.language     used to decide whether translation is needed

---------------------------------------------------------------------------
Outputs
---------------------------------------------------------------------------

  step_outputs.preprocess.output =
      Step1PreprocessOutput {
          frames:                [ExtractedFrame{frame_id, timestamp_seconds,
                                                local_path, ocr_text}]
          transcript:            str
          transcript_language:   str | None
          transcript_translated: str | None
          nothing_to_extract:    bool
      }

---------------------------------------------------------------------------
Model
---------------------------------------------------------------------------

No LLM. This step is deterministic extraction (OpenCV / Whisper / EasyOCR /
translation). If an LLM is ever used for translation, it must go through the
provider boundary in src/laclaugpt_data_analysis/llm/ and be recorded in
provenance like any other model call.

---------------------------------------------------------------------------
Uncertainty
---------------------------------------------------------------------------

  no media present          -> StepStatus.SKIPPED, nothing_to_extract=True
  a frame fails to extract  -> keep going, record the frame as absent in notes
  no audio track            -> transcript="" (valid: INV_ABSTAIN)
  translation unavailable   -> transcript_translated=None, not ""

---------------------------------------------------------------------------
Provenance
---------------------------------------------------------------------------

Record, per extracted artefact: the local path, and for the transcript the
provider and the language detected. The media's checksum (when collection
supplied one) is carried onto the frame so a re-extraction can be detected.

---------------------------------------------------------------------------
"""
from __future__ import annotations

from models.incoming import IncomingRecord
from models.steps import Step1PreprocessOutput

from steps import StepContext, StepResult, StepStatus


def run(record: IncomingRecord, *, context: StepContext) -> StepResult:
    """Extract frames, OCR, transcript and translation for one record.

    TO HAND-CODE (step 2 of issue #315). The body below is the shape, not the
    method. Fill it in keeping the Inputs / Outputs sections above accurate; if
    they need to change, change them deliberately and say so.
    """
    if not record.has_media:
        # A text-only record is valid. This step simply has nothing to do.
        return StepResult(
            status=StepStatus.SKIPPED,
            output=Step1PreprocessOutput(nothing_to_extract=True),
            notes=["record has no media; nothing to extract"],
        )

    # ---------------------------------------------------------------- TO CODE
    # Expected shape of the finished body, for readability:
    #
    #   frames = []
    #   for item in record.video_items:
    #       frames.extend(extract_frames(item))
    #   for frame in frames:
    #       frame.ocr_text = read_text(frame)
    #   transcript, language = transcribe(record.video_items)
    #   translated = translate(transcript, language) if needs_translation(language) else None
    #   return StepResult(output=Step1PreprocessOutput(
    #       frames=frames,
    #       transcript=transcript,
    #       transcript_language=language,
    #       transcript_translated=translated,
    #   ))
    raise NotImplementedError(
        "step 1 (preprocess) is hand-coded by the researcher; see the module docstring"
    )
