"""Prepare private AI26 network input from existing canonical DNA coding.

No inference or model calls: exact quotations, explicit identity mapping,
binary coding and provenance are required. Observed SNA relations must be
provided separately as existing SNARelation objects.
"""

from __future__ import annotations

import hashlib
import json

from laclaugpt_data_analysis.discourse_network.models import DiscourseStatement as NativeStatement
from laclaugpt_data_analysis.interoperability import DiscourseStatement


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def convert_coded_record(record, identities):
    """Return interoperable DNA statements from the current successful coding.

    identities maps native actor/concept IDs to reviewed canonical IDs;
    unmapped identities, abstentions and mismatched quotes are excluded.
    """
    analysis = record.get("analysis", {})
    if analysis.get("plugin_failures", {}).get("dna_statement_coding"):
        return []
    payload = analysis.get("plugin_results", {}).get("dna_statement_coding", {})
    run = payload.get("model_run")
    if not run:
        return []
    text = record.get("content", {}).get("text", "")
    source_url = record["source_url"]
    statements = []
    for raw in payload.get("proposal", {}).get("statements", []):
        native = NativeStatement.model_validate(raw)
        if native.source_url != source_url:
            raise ValueError("DNA coding belongs to another source")
        if native.abstained or native.agreement is None:
            continue
        if native.validation_status in {"rejected", "needs_review"}:
            continue
        span = native.evidence
        if (
            not span.exact or not span.quote
            or span.start_char is None or span.end_char is None
            or text[span.start_char:span.end_char] != span.quote
        ):
            continue
        actor = identities.get("actors", {}).get(native.actor_id)
        concept = identities.get("concepts", {}).get(native.concept_id)
        if not actor or not concept or actor == concept:
            continue
        coder = native.coder_id_or_model
        if not coder:
            continue
        producer_type = "human" if native.coder_type == "human" else "model"
        statement = DiscourseStatement(
            statement_id=native.statement_id,
            actor_id=actor,
            actor_label=native.actor_name,
            concept_id=concept,
            concept_label=native.concept_label,
            qualifier="agree" if native.agreement else "disagree",
            source_url=source_url,
            source_document_id=native.source_record_id or source_url,
            evidence_id="dna-evidence:" + _digest([source_url, span.model_dump(mode="json")]),
            evidence_text=span.quote,
            timestamp=native.timestamp,
            producer={"type": producer_type, "id": coder, "version": native.model_version},
            provenance_id="dna-run:" + _digest([source_url, run, native.provenance]),
            confidence=native.confidence,
            document_attributes={"evidence_span": span.model_dump(mode="json"),
                                 "model_run": run, "native_provenance": native.provenance},
            actor_attributes={"native_actor_id": native.actor_id,
                              "native_concept_id": native.concept_id},
        )
        # Do not promote a candidate to a validated claim during export.
        statements.append(statement.model_dump(mode="json"))
    return statements
