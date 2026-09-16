"""Adapters from canonical records to the shared evidence-linked claim layer."""
from __future__ import annotations

import hashlib
from typing import Any

from .canonical import CanonicalRecord
from .discourse_network.models import DiscourseStatement, EvidenceSpan


def stable_statement_id(
    *,
    source_url: str,
    actor_id: str,
    concept_id: str,
    start_char: int | None,
    end_char: int | None,
    proposition: str | None,
) -> str:
    payload = "|".join(
        [
            source_url,
            actor_id,
            concept_id,
            "" if start_char is None else str(start_char),
            "" if end_char is None else str(end_char),
            proposition or "",
        ]
    )
    return "stmt-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def claim_from_canonical(
    record: CanonicalRecord,
    proposal: dict[str, Any],
    *,
    project_id: str,
    arena: str | None = None,
    codebook_version: str | None = None,
) -> DiscourseStatement:
    """Combine a canonical record with an explicit coder/model claim proposal.

    This function does not discover claims. It validates and binds an already produced
    proposal to canonical source identity/evidence so downstream DNA/framing/MCA joins
    cannot lose provenance. Unsupported proposals should set `abstained=True`.
    """
    actor_id = str(proposal.get("actor_id") or "").strip()
    actor_name = str(proposal.get("actor_name") or actor_id).strip()
    concept_id = str(proposal.get("concept_id") or "").strip()
    concept_label = str(proposal.get("concept_label") or concept_id).strip()
    abstained = bool(proposal.get("abstained", False))
    if not actor_id or not concept_id:
        raise ValueError("claim proposal requires actor_id and concept_id")

    quote = str(proposal.get("evidence_quote") or "")
    start = proposal.get("evidence_start")
    end = proposal.get("evidence_end")
    exact = False
    if start is not None or end is not None:
        if start is None or end is None:
            raise ValueError("evidence_start and evidence_end must be supplied together")
        if not isinstance(start, int) or not isinstance(end, int):
            raise TypeError("evidence offsets must be integers")
        text = record.content.text or ""
        if start < 0 or end <= start or end > len(text):
            raise ValueError("evidence offsets are outside canonical content.text")
        exact = not quote or text[start:end] == quote
        if quote and not exact and not abstained:
            raise ValueError("evidence quote does not match canonical content.text offsets")
        if not quote:
            quote = text[start:end]
            exact = True
    elif quote and record.content.text:
        found = record.content.text.find(quote)
        if found >= 0:
            start, end, exact = found, found + len(quote), True

    proposition = proposal.get("proposition")
    if proposition and not quote and not abstained:
        raise ValueError("grounded proposition requires source evidence")

    statement_id = str(proposal.get("statement_id") or "").strip() or stable_statement_id(
        source_url=record.source_url,
        actor_id=actor_id,
        concept_id=concept_id,
        start_char=start,
        end_char=end,
        proposition=str(proposition) if proposition is not None else None,
    )
    source_record_id = proposal.get("source_record_id")
    if source_record_id is None:
        source_record_id = record.source_native_ids.get("canonical") or record.source_native_ids.get("id")

    return DiscourseStatement(
        statement_id=statement_id,
        source_url=record.source_url,
        source_record_id=source_record_id,
        actor_id=actor_id,
        actor_name=actor_name,
        target_actor_id=proposal.get("target_actor_id"),
        target_actor_name=proposal.get("target_actor_name"),
        concept_id=concept_id,
        concept_label=concept_label,
        original_concept_wording=proposal.get("original_concept_wording"),
        proposition=proposition,
        concept_type=proposal.get("concept_type", "concept"),
        stance=proposal.get("stance", "unknown"),
        polarity=proposal.get("polarity"),
        relation_type=proposal.get("relation_type"),
        timestamp=proposal.get("timestamp") or record.source.created_at,
        evidence=EvidenceSpan(quote=quote, start_char=start, end_char=end, exact=exact),
        collection_id=proposal.get("collection_id"),
        project_id=project_id,
        arena=arena or proposal.get("arena"),
        platform=proposal.get("platform") or record.source.platform or None,
        coder_type=proposal.get("coder_type", "unknown"),
        coder_id_or_model=proposal.get("coder_id_or_model"),
        model_provider=proposal.get("model_provider"),
        model_version=proposal.get("model_version"),
        confidence=proposal.get("confidence"),
        codebook_version=codebook_version or proposal.get("codebook_version"),
        validation_status=proposal.get("validation_status", "provisional"),
        abstained=abstained,
        reviewed_by=proposal.get("reviewed_by"),
        reviewed_at=proposal.get("reviewed_at"),
        correction_note=proposal.get("correction_note"),
        metadata=dict(proposal.get("metadata") or {}),
        provenance={
            "canonical_schema_version": record.schema_version,
            "record_review_status": record.review.status,
            **dict(proposal.get("provenance") or {}),
        },
    )
