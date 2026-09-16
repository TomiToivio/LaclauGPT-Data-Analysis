"""Transparent CSV interchange for Discourse Network Analysis statements."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from ...discourse_network.models import DiscourseStatement, EvidenceSpan

_FIELDS = [
    "statement_id", "source_url", "source_record_id", "actor_id", "actor_name",
    "concept_id", "concept_label", "concept_type", "stance", "polarity",
    "relation_type", "timestamp", "evidence", "evidence_start", "evidence_stop",
    "evidence_exact", "collection_id", "coder_type", "coder_id_or_model",
    "confidence", "codebook_version", "validation_status", "provenance_json",
]


def export_dna_statements_csv(statements: list[DiscourseStatement], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDS)
        writer.writeheader()
        for s in statements:
            writer.writerow({
                "statement_id": s.statement_id,
                "source_url": s.source_url,
                "source_record_id": s.source_record_id or "",
                "actor_id": s.actor_id,
                "actor_name": s.actor_name,
                "concept_id": s.concept_id,
                "concept_label": s.concept_label,
                "concept_type": s.concept_type.value,
                "stance": s.stance.value,
                "polarity": "" if s.polarity is None else s.polarity,
                "relation_type": s.relation_type or "",
                "timestamp": "" if s.timestamp is None else s.timestamp.isoformat(),
                "evidence": s.evidence.quote,
                "evidence_start": "" if s.evidence.start_char is None else s.evidence.start_char,
                "evidence_stop": "" if s.evidence.end_char is None else s.evidence.end_char,
                "evidence_exact": int(s.evidence.exact),
                "collection_id": s.collection_id or "",
                "coder_type": s.coder_type,
                "coder_id_or_model": s.coder_id_or_model or "",
                "confidence": "" if s.confidence is None else s.confidence,
                "codebook_version": s.codebook_version or "",
                "validation_status": s.validation_status.value,
                "provenance_json": json.dumps(s.provenance, ensure_ascii=False, sort_keys=True),
            })
    return out


def _none(value: str) -> str | None:
    value = value.strip()
    return value or None


def import_dna_statements_csv(path: str | Path) -> list[DiscourseStatement]:
    rows: list[DiscourseStatement] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            provenance = json.loads(row.get("provenance_json") or "{}")
            rows.append(DiscourseStatement(
                statement_id=row["statement_id"],
                source_url=row["source_url"],
                source_record_id=_none(row.get("source_record_id", "")),
                actor_id=row["actor_id"],
                actor_name=row["actor_name"],
                concept_id=row["concept_id"],
                concept_label=row["concept_label"],
                concept_type=row.get("concept_type") or "concept",
                stance=row.get("stance") or "unknown",
                polarity=float(row["polarity"]) if row.get("polarity") else None,
                relation_type=_none(row.get("relation_type", "")),
                timestamp=datetime.fromisoformat(row["timestamp"]) if row.get("timestamp") else None,
                evidence=EvidenceSpan(
                    quote=row.get("evidence") or "",
                    start_char=int(row["evidence_start"]) if row.get("evidence_start") else None,
                    end_char=int(row["evidence_stop"]) if row.get("evidence_stop") else None,
                    exact=(row.get("evidence_exact") or "0").lower() in {"1", "true", "yes"},
                ),
                collection_id=_none(row.get("collection_id", "")),
                coder_type=row.get("coder_type") or "unknown",
                coder_id_or_model=_none(row.get("coder_id_or_model", "")),
                confidence=float(row["confidence"]) if row.get("confidence") else None,
                codebook_version=_none(row.get("codebook_version", "")),
                validation_status=row.get("validation_status") or "provisional",
                provenance=provenance,
            ))
    return rows
