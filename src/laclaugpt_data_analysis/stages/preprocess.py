"""Stage 1 — preprocess: enrich the source record before any model sees it.

Purpose
-------
Turn a raw canonical record into one that carries all the *derived inputs* the
later stages can use: transcript (ASR), visible text (OCR), video keyframes and
translations. This stage never interprets the material.

Why it exists as its own step
-----------------------------
Extraction is expensive and fallible, and different studies have different
capabilities (one corpus has video, another is text-only). Keeping enrichment in
one place means:

* the later stages can be written as if derived inputs already exist;
* extraction failures stay attributable to extraction, not to interpretation;
* the run can be reproduced without re-deriving media.

Scientific boundary
-------------------
Preprocess adds *representations of the source*, not *claims about it*. Nothing
here may classify, summarise or evaluate. That boundary is what lets a
researcher treat everything after this stage as a proposal rather than a fact.

Inputs
------
* `record` — the canonical record to enrich.
* `preprocessor` — optional callable performing the actual media work
  (typically an ASR/OCR/keyframe toolchain, injected so the same pipeline runs
  on a laptop or a compute cluster).

Outputs
-------
The same record, mutated in place:
* `record.intermediate.asr / ocr / frames / translations` — extended with
  whatever the preprocessor produced;
* `record.legacy` — any legacy fields the preprocessor reports;
* stage outputs `preprocess` (when the preprocessor reports one) and
  `preprocess_contract` (always) recording that source and legacy fields were
  preserved.
"""
from __future__ import annotations

from ..canonical import CanonicalRecord
from .shared import Preprocessor, append_stage, now_iso


def preprocess_record(
    record: CanonicalRecord, *, preprocessor: Preprocessor | None = None
) -> CanonicalRecord:
    """Apply the (optional) preprocessor and record the preservation contract."""
    payload = preprocessor(record) if preprocessor else None
    if payload:
        for key in ("asr", "ocr", "frames", "translations"):
            values = payload.get(key)
            if values:
                getattr(record.intermediate, key).extend(values)
        if payload.get("legacy"):
            record.legacy.update(payload["legacy"])
        if payload.get("stage_output"):
            append_stage(record, "preprocess", payload["stage_output"])

    # Record that the source was left intact. Derived inputs may be added but the
    # captured source and any legacy fields must survive untouched, so a reviewer
    # can always see the original material behind an analysis.
    append_stage(
        record,
        "preprocess_contract",
        {
            "created_at": now_iso(),
            "source_preserved": record.raw_capture.preserved or bool(record.source.raw_metadata),
            "legacy_fields_preserved": sorted(record.legacy),
        },
    )
    return record
