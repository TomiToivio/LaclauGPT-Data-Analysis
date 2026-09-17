"""Complete normalized DATS project adapter built on the core interchange models."""
from __future__ import annotations

from typing import Any

from .dats_review import import_dats_human_correction
from .interoperability import (
    DatsProject,
    ExternalRef,
    Producer,
    ResearchNote,
    TemporalPoint,
    TemporalSeries,
    export_dats_project,
    import_dats_project,
)


def import_project(payload: dict[str, Any]) -> DatsProject:
    """Import normalized DATS project data including qualitative workflow objects."""
    project = import_dats_project(payload)

    code_by_dats_id = {
        ref.id: code.code_id
        for code in project.codes
        for ref in code.external_ids
        if ref.system == "dats"
    }
    for code in project.codes:
        if code.parent_id in code_by_dats_id:
            code.parent_id = code_by_dats_id[code.parent_id]
    for annotation in project.annotations:
        if annotation.code_id in code_by_dats_id:
            annotation.code_id = code_by_dats_id[annotation.code_id]

    project.notes = [
        ResearchNote(
            note_id=str(item.get("canonical_id") or f"dats-note:{item['id']}"),
            text=str(item.get("text", "")),
            source_url=item.get("source_url"),
            producer=Producer(
                type=item.get("producer_type", "human"),
                id=str(item.get("producer_id", "unknown")),
                version=item.get("producer_version"),
            ),
            external_ids=[ExternalRef(system="dats", id=str(item["id"]))],
        )
        for item in payload.get("notes", payload.get("memos", []))
    ]

    project.reviews = [
        import_dats_human_correction(item)
        for item in payload.get("reviews", payload.get("corrections", []))
    ]

    project.temporal_series = [
        TemporalSeries(
            series_id=str(item.get("canonical_id") or f"dats-series:{item['id']}"),
            label=str(item["label"]),
            unit=str(item.get("unit", "count")),
            points=[TemporalPoint.model_validate(point) for point in item.get("points", [])],
            producer=Producer(
                type=item.get("producer_type", "tool"),
                id=str(item.get("producer_id", "dats")),
                version=item.get("producer_version"),
            ),
            parameters=item.get("parameters", {}),
            external_ids=[ExternalRef(system="dats", id=str(item["id"]))],
        )
        for item in payload.get("temporal_series", [])
    ]

    project.relations = [
        {
            "relation_id": str(item.get("canonical_id") or f"dats-relation:{item['id']}"),
            "external_ids": {"dats": str(item["id"])},
            "source_ref": str(item["source_ref"]),
            "target_ref": str(item["target_ref"]),
            "relation_type": str(item.get("relation_type", "whiteboard_relation")),
            "producer": {
                "type": item.get("producer_type", "human"),
                "id": str(item.get("producer_id", "unknown")),
            },
            "review_status": item.get("review_status", "PROVISIONAL"),
            "metadata": item.get("metadata", {}),
        }
        for item in payload.get("relations", payload.get("whiteboard_relations", []))
    ]
    return project


def export_project(project: DatsProject) -> dict[str, Any]:
    """Export the normalized DATS profile including extended workflow objects."""
    payload = export_dats_project(project)
    code_external = {}
    for code in project.codes:
        external = next((ref.id for ref in code.external_ids if ref.system == "dats"), None)
        code_external[code.code_id] = external or code.code_id

    for code in payload["codes"]:
        parent = code.get("parent_id")
        if parent in code_external:
            code["parent_id"] = code_external[parent]
    for annotation in payload["annotations"]:
        code_id = annotation.get("code_id")
        if code_id in code_external:
            annotation["code_id"] = code_external[code_id]

    payload["notes"] = [
        {
            "id": next((ref.id for ref in note.external_ids if ref.system == "dats"), note.note_id),
            "canonical_id": note.note_id,
            "text": note.text,
            "source_url": note.source_url,
            "producer_type": note.producer.type,
            "producer_id": note.producer.id,
            "producer_version": note.producer.version,
        }
        for note in project.notes
    ]
    payload["reviews"] = [review.model_dump(mode="json") for review in project.reviews]
    payload["temporal_series"] = [series.model_dump(mode="json") for series in project.temporal_series]
    payload["relations"] = list(project.relations)
    return payload
