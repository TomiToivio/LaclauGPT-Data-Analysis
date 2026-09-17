"""Portable DATS/DNA interoperability contracts for LaclauGPT Data Analysis.

External formats are adapters around the canonical LaclauGPT record. Imported
results remain descriptive/namespaced and machine proposals remain provisional
until explicit human review.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from .canonical import CanonicalRecord, Evidence, ReviewStatus
from .models import Model

INTEROP_SCHEMA_VERSION = "1.0.0"
ProducerType = Literal["human", "model", "tool"]


class Producer(Model):
    type: ProducerType
    id: str
    version: str | None = None


class ExternalRef(Model):
    system: str
    id: str


class Code(Model):
    code_id: str
    label: str
    parent_id: str | None = None
    description: str | None = None
    external_ids: list[ExternalRef] = Field(default_factory=list)


class Annotation(Model):
    annotation_id: str
    source_url: str
    evidence_id: str
    code_id: str
    producer: Producer
    review_status: ReviewStatus = "PROVISIONAL"
    confidence: float | None = Field(default=None, ge=0, le=1)
    external_ids: list[ExternalRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchNote(Model):
    note_id: str
    text: str
    producer: Producer
    source_url: str | None = None
    external_ids: list[ExternalRef] = Field(default_factory=list)


class HumanReview(Model):
    review_id: str
    target_id: str
    reviewer: str
    decision: ReviewStatus
    reviewed_at: datetime
    note: str | None = None
    corrections: dict[str, Any] = Field(default_factory=dict)
    external_ids: list[ExternalRef] = Field(default_factory=list)


class TemporalPoint(Model):
    timestamp: datetime
    value: float
    count: int | None = None


class TemporalSeries(Model):
    series_id: str
    label: str
    unit: str
    points: list[TemporalPoint]
    producer: Producer
    parameters: dict[str, Any] = Field(default_factory=dict)
    external_ids: list[ExternalRef] = Field(default_factory=list)


class DiscourseStatement(Model):
    """Theory-neutral bridge object for DNA/rDNA statement coding."""

    schema_version: str = INTEROP_SCHEMA_VERSION
    statement_id: str
    actor_id: str
    actor_label: str
    concept_id: str
    concept_label: str
    qualifier: str | None = None
    source_url: str
    source_document_id: str
    evidence_id: str | None = None
    evidence_text: str | None = None
    timestamp: datetime | None = None
    actor_attributes: dict[str, Any] = Field(default_factory=dict)
    document_attributes: dict[str, Any] = Field(default_factory=dict)
    producer: Producer
    confidence: float | None = Field(default=None, ge=0, le=1)
    uncertainty: str | None = None
    provenance_id: str | None = None
    review_status: ReviewStatus = "PROVISIONAL"
    external_ids: list[ExternalRef] = Field(default_factory=list)

    @field_validator("source_url")
    @classmethod
    def source_identity_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source_url is required for round-trip identity")
        return value


class GraphProjection(Model):
    projection_id: str
    graph_type: str
    node_semantics: str
    edge_semantics: str
    weighting_method: str
    projection_method: str
    temporal_scope: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    source_statement_ids: list[str] = Field(default_factory=list)
    producer: Producer
    provenance_id: str | None = None


class DatsProject(Model):
    schema_version: str = INTEROP_SCHEMA_VERSION
    project_id: str
    documents: list[CanonicalRecord] = Field(default_factory=list)
    codes: list[Code] = Field(default_factory=list)
    annotations: list[Annotation] = Field(default_factory=list)
    notes: list[ResearchNote] = Field(default_factory=list)
    reviews: list[HumanReview] = Field(default_factory=list)
    temporal_series: list[TemporalSeries] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    external_metadata: dict[str, Any] = Field(default_factory=dict)


def _external_id(refs: list[ExternalRef], system: str) -> str | None:
    return next((ref.id for ref in refs if ref.system == system), None)


def import_dats_project(payload: dict[str, Any]) -> DatsProject:
    """Import the normalized DATS interchange profile.

    The adapter deliberately accepts a documented neutral profile rather than
    depending on DATS internals. Tool-specific exporters can map native DATS
    project bundles into this profile at the boundary.
    """
    documents: list[CanonicalRecord] = []
    for item in payload.get("documents", []):
        dats_id = str(item["id"])
        source_url = item.get("source_url") or f"dats:document:{dats_id}"
        documents.append(
            CanonicalRecord(
                source_url=source_url,
                source_native_ids={"dats_document_id": dats_id},
                source={
                    "platform": item.get("platform", "dats"),
                    "source_type": item.get("source_type", "document"),
                    "language": item.get("language", ""),
                    "raw_metadata": item.get("metadata", {}),
                },
                content={
                    "text": item.get("text", ""),
                    "title": item.get("title"),
                    "language": item.get("language"),
                    "media_references": item.get("media_references", []),
                },
            )
        )

    codes = [
        Code(
            code_id=str(c.get("canonical_id") or f"dats-code:{c['id']}"),
            label=c["label"],
            parent_id=c.get("parent_id"),
            description=c.get("description"),
            external_ids=[ExternalRef(system="dats", id=str(c["id"]))],
        )
        for c in payload.get("codes", [])
    ]

    doc_by_dats = {r.source_native_ids["dats_document_id"]: r for r in documents}
    annotations: list[Annotation] = []
    for ann in payload.get("annotations", []):
        record = doc_by_dats[str(ann["document_id"])]
        start, end = int(ann["start"]), int(ann["end"])
        text = record.content.text
        if start < 0 or end < start or end > len(text):
            raise ValueError(f"Invalid DATS annotation span {start}:{end}")
        evidence_id = str(ann.get("evidence_id") or f"dats-evidence:{ann['id']}")
        evidence = Evidence(
            evidence_id=evidence_id,
            kind="text-span",
            source_url=record.source_url,
            quote=text[start:end],
            start_offset=start,
            end_offset=end,
            metadata={"external_ids": {"dats_annotation_id": str(ann["id"])}},
        )
        record.evidence.append(evidence)
        producer_type = ann.get("producer_type", "human")
        review_status: ReviewStatus = ann.get(
            "review_status", "PROVISIONAL" if producer_type != "human" else "ACCEPTED"
        )
        annotations.append(
            Annotation(
                annotation_id=str(ann.get("canonical_id") or f"dats-annotation:{ann['id']}"),
                source_url=record.source_url,
                evidence_id=evidence_id,
                code_id=str(ann.get("code_id")),
                producer=Producer(
                    type=producer_type,
                    id=str(ann.get("producer_id", "unknown")),
                    version=ann.get("producer_version"),
                ),
                review_status=review_status,
                confidence=ann.get("confidence"),
                external_ids=[ExternalRef(system="dats", id=str(ann["id"]))],
                metadata=ann.get("metadata", {}),
            )
        )

    return DatsProject(
        project_id=str(payload.get("project_id", "dats-project")),
        documents=documents,
        codes=codes,
        annotations=annotations,
        external_metadata=payload.get("metadata", {}),
    )


def export_dats_project(project: DatsProject) -> dict[str, Any]:
    """Export a normalized DATS profile while retaining provisional AI status."""
    doc_ids: dict[str, str] = {}
    docs = []
    for record in project.documents:
        dats_id = record.source_native_ids.get("dats_document_id", record.source_url)
        doc_ids[record.source_url] = dats_id
        docs.append(
            {
                "id": dats_id,
                "source_url": record.source_url,
                "title": record.content.title,
                "text": record.content.text,
                "language": record.content.language or record.source.language,
                "metadata": record.source.raw_metadata,
            }
        )

    evidence = {
        ev.evidence_id: ev for record in project.documents for ev in record.evidence
    }
    annotations = []
    for ann in project.annotations:
        ev = evidence.get(ann.evidence_id)
        if ev is None or ev.start_offset is None or ev.end_offset is None:
            raise ValueError(f"Annotation {ann.annotation_id} lacks reconstructable text offsets")
        annotations.append(
            {
                "id": _external_id(ann.external_ids, "dats") or ann.annotation_id,
                "document_id": doc_ids[ann.source_url],
                "code_id": ann.code_id,
                "start": ev.start_offset,
                "end": ev.end_offset,
                "producer_type": ann.producer.type,
                "producer_id": ann.producer.id,
                "producer_version": ann.producer.version,
                "review_status": ann.review_status,
                "confidence": ann.confidence,
                "provisional_ai": ann.producer.type == "model" and ann.review_status == "PROVISIONAL",
                "metadata": ann.metadata,
            }
        )

    return {
        "schema_version": project.schema_version,
        "project_id": project.project_id,
        "documents": docs,
        "codes": [
            {
                "id": _external_id(code.external_ids, "dats") or code.code_id,
                "canonical_id": code.code_id,
                "label": code.label,
                "parent_id": code.parent_id,
                "description": code.description,
            }
            for code in project.codes
        ],
        "annotations": annotations,
        "metadata": project.external_metadata,
    }


def import_dna_rows(rows: list[dict[str, Any]]) -> list[DiscourseStatement]:
    statements: list[DiscourseStatement] = []
    for row in rows:
        dna_id = str(row.get("statement_id") or row.get("id") or "")
        if not dna_id:
            raise ValueError("DNA row requires statement_id/id")
        statements.append(
            DiscourseStatement(
                statement_id=str(row.get("canonical_id") or f"dna:{dna_id}"),
                actor_id=str(row["actor_id"]),
                actor_label=str(row.get("actor_label", row["actor_id"])),
                concept_id=str(row["concept_id"]),
                concept_label=str(row.get("concept_label", row["concept_id"])),
                qualifier=row.get("qualifier"),
                source_url=str(row["source_url"]),
                source_document_id=str(row.get("document_id", row["source_url"])),
                evidence_id=row.get("evidence_id"),
                evidence_text=row.get("evidence_text"),
                timestamp=row.get("timestamp"),
                actor_attributes=_json_object(row.get("actor_attributes")),
                document_attributes=_json_object(row.get("document_attributes")),
                producer=Producer(
                    type=row.get("producer_type", "human"),
                    id=str(row.get("producer_id", "unknown")),
                    version=row.get("producer_version"),
                ),
                confidence=_optional_float(row.get("confidence")),
                uncertainty=row.get("uncertainty"),
                provenance_id=row.get("provenance_id"),
                review_status=row.get("review_status", "PROVISIONAL"),
                external_ids=[ExternalRef(system="dna", id=dna_id)],
            )
        )
    return statements


def export_dna_rows(statements: list[DiscourseStatement]) -> list[dict[str, Any]]:
    return [
        {
            "statement_id": _external_id(s.external_ids, "dna") or s.statement_id,
            "canonical_id": s.statement_id,
            "actor_id": s.actor_id,
            "actor_label": s.actor_label,
            "concept_id": s.concept_id,
            "concept_label": s.concept_label,
            "qualifier": s.qualifier,
            "source_url": s.source_url,
            "document_id": s.source_document_id,
            "evidence_id": s.evidence_id,
            "evidence_text": s.evidence_text,
            "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            "actor_attributes": json.dumps(s.actor_attributes, ensure_ascii=False, sort_keys=True),
            "document_attributes": json.dumps(
                s.document_attributes, ensure_ascii=False, sort_keys=True
            ),
            "producer_type": s.producer.type,
            "producer_id": s.producer.id,
            "producer_version": s.producer.version,
            "confidence": s.confidence,
            "uncertainty": s.uncertainty,
            "provenance_id": s.provenance_id,
            "review_status": s.review_status,
        }
        for s in statements
    ]


def dna_csv_dumps(statements: list[DiscourseStatement]) -> str:
    rows = export_dna_rows(statements)
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def dna_csv_loads(text: str) -> list[DiscourseStatement]:
    return import_dna_rows(list(csv.DictReader(io.StringIO(text))))


def attach_external_result(
    record: CanonicalRecord,
    *,
    namespace: str,
    result: dict[str, Any],
    producer: Producer,
    parameters: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> None:
    """Attach external descriptive output without promoting it to theory claims."""
    record.analysis.plugin_results[namespace] = {
        "schema_version": INTEROP_SCHEMA_VERSION,
        "producer": producer.model_dump(mode="json"),
        "parameters": parameters or {},
        "run_id": run_id,
        "result": result,
        "interpretation_status": "DESCRIPTIVE_ONLY",
    }


def _json_object(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    parsed = json.loads(str(value))
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object")
    return parsed


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
