"""Source-evidence gate: abstain instead of interpreting nothing.

Phase 1's stated rule is evidence-first: an interpretation is attributable to
the source it read. A record can nevertheless reach the interpretive stages
with no usable source evidence at all — no text, no transcript, no OCR, no
frame description. In that state the model still answers, because a prompt with
an empty source and a title still looks like a task; it produces a formation, a
signifier and an antagonism out of the record's metadata and its prior about
the platform (issue #451).

This module makes that state explicit and mechanical. It answers one question —
*is there source evidence for an interpretation to read?* — and, when the answer
is no, writes an abstention instead of an interpretation:

* ``analysis.status = "no_evidence"`` (the schema already carries
  ``abstentions`` and ``uncertainty`` for exactly this);
* a human-readable abstention saying why;
* an ``evidence_gate`` stage entry recording the decision, so a reviewer can
  tell "nothing was coded" from "coding was attempted and abstained".

The gate is deliberately conservative about what counts as evidence. Metadata
(title, handle, domain, link card) is *not* source evidence: it may route a
record, but it cannot substantiate a claim about what the source argues.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..canonical import CanonicalRecord
from .shared import append_stage

#: The reason string is part of the exported record, so it is stable prose a
#: reviewer and an audit can rely on rather than a log message.
NO_SOURCE_EVIDENCE_REASON = "no usable source evidence: interpretation abstained"


def _text_items(record: CanonicalRecord) -> dict[str, list[str]]:
    """Return the text actually available to an interpretive stage, per modality.

    Only materialised text counts. ``media_references`` and ``file_references``
    are pointers, not evidence: a URL that was never fetched, or a video that was
    never transcribed, cannot substantiate a quotation.
    """
    content = record.content
    return {
        "text": [(content.text or "").strip()],
        "translated_text": [(content.translated_text or "").strip()],
        "transcripts": [item.text.strip() for item in content.transcripts if (item.text or "").strip()],
        "ocr": [item.text.strip() for item in content.ocr if (item.text or "").strip()],
        "frames": [
            (item.description or "").strip()
            for item in content.frames
            if (item.description or "").strip()
        ],
    }


def source_evidence(record: CanonicalRecord) -> dict[str, Any]:
    """Describe the source evidence available to an interpretive stage.

    ``available`` is true when at least one modality carries materialised text.
    ``chars`` counts the same characters the prompt would be given, so a caller
    can log *how much* evidence there was rather than only whether there was any.
    """
    modalities = _text_items(record)
    per_modality = {name: sum(len(item) for item in items) for name, items in modalities.items()}
    chars = sum(per_modality.values())
    return {
        "available": chars > 0,
        "chars": chars,
        "modalities": {name: count for name, count in per_modality.items() if count},
        "declared_media": len(record.content.media_references),
        "materialized_frames": len(record.content.frames),
    }


def abstain_without_source_evidence(
    record: CanonicalRecord,
    *,
    stage: str,
    policy: str = "evidence_first_v1",
) -> bool:
    """Abstain and record why when the record carries no usable source evidence.

    Returns ``True`` when the caller must stop before the interpretive stages,
    ``False`` when there is evidence and the pipeline should proceed normally.
    Idempotent: a second call appends a second gate entry (the audit trail is
    append-only) but does not duplicate the abstention text.
    """
    evidence = source_evidence(record)
    if evidence["available"]:
        return False

    if NO_SOURCE_EVIDENCE_REASON not in record.analysis.abstentions:
        record.analysis.abstentions.append(NO_SOURCE_EVIDENCE_REASON)
    uncertainty_note = (
        "source text is empty; a formation, signifier or antagonism here would "
        "be derived from metadata rather than from source evidence"
    )
    if uncertainty_note not in record.analysis.uncertainty:
        record.analysis.uncertainty.append(uncertainty_note)

    # `no_evidence` is the status the schema and the review export already reserve
    # for a record that was collected and routed but not interpreted. It must not
    # read as a successful analysis, which is what happens today.
    record.analysis.status = "no_evidence"
    record.analysis.completed_at = datetime.now(UTC)

    append_stage(
        record,
        "evidence_gate",
        {
            "created_at": datetime.now(UTC).isoformat(),
            "decision": "abstain",
            "policy": policy,
            "stage": stage,
            "reason": "no_source_evidence",
            **evidence,
        },
    )
    return True
