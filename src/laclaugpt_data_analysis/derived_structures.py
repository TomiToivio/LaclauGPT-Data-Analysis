"""Visualization-ready location, timeline and discourse-network projections.

These structures are derived from the canonical record and remain rebuildable.  They do
not replace source evidence and do not silently promote inferred/geocoded locations to
source-provided facts.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Literal, Protocol

from pydantic import Field

from .canonical import CanonicalRecord, ReviewStatus
from .models import Model

LocationOrigin = Literal["source", "inferred", "geocoded"]


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(payload).hexdigest()[:20]}"


def normalize_location_name(value: str) -> str:
    """Normalize display location text without pretending to resolve geography."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


class LocationEntity(Model):
    location_id: str
    name: str
    normalized_name: str
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    country: str = ""
    region: str = ""
    source_url: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    origin: LocationOrigin
    extraction_method: str = ""
    geocoder: str = ""
    review_status: ReviewStatus = "PROVISIONAL"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimelineEvent(Model):
    event_id: str
    label: str
    description: str = ""
    time_text: str = ""
    source_url: str
    location_ids: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    entity_refs: list[str] = Field(default_factory=list)
    signifier_refs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    extraction_method: str = ""
    review_status: ReviewStatus = "PROVISIONAL"
    metadata: dict[str, Any] = Field(default_factory=dict)


class NetworkRelation(Model):
    relation_id: str
    source_ref: str
    target_ref: str
    relation_type: str
    source_url: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    review_status: ReviewStatus = "PROVISIONAL"
    provenance: str = "canonical-analysis"
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeocodeResult(Model):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    normalized_name: str = ""
    country: str = ""
    region: str = ""
    confidence: float | None = Field(default=None, ge=0, le=1)
    provider: str = ""


class Geocoder(Protocol):
    def geocode(self, name: str) -> GeocodeResult | None: ...


def _summary_event_candidates(record: CanonicalRecord) -> list[dict[str, Any]]:
    output = record.intermediate.stage_outputs.get("summary_preanalysis")
    rows = output if isinstance(output, list) else ([] if output is None else [output])
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        proposal = row.get("proposal")
        if not isinstance(proposal, dict):
            continue
        events = proposal.get("event_candidates")
        if isinstance(events, list):
            candidates.extend(event for event in events if isinstance(event, dict))
    return candidates


def _source_location(record: CanonicalRecord) -> LocationEntity | None:
    raw = record.source.raw_metadata
    value = raw.get("location") or raw.get("place") or raw.get("source_location")
    if not isinstance(value, str) or not value.strip():
        return None
    latitude = raw.get("latitude") or raw.get("lat")
    longitude = raw.get("longitude") or raw.get("lng") or raw.get("lon")
    try:
        lat = float(latitude) if latitude not in (None, "") else None
        lon = float(longitude) if longitude not in (None, "") else None
    except (TypeError, ValueError):
        lat = lon = None
    name = value.strip()
    return LocationEntity(
        location_id=_stable_id("location", record.source_url, "source", normalize_location_name(name)),
        name=name,
        normalized_name=normalize_location_name(name),
        latitude=lat,
        longitude=lon,
        country=record.source.country,
        source_url=record.source_url,
        confidence=1.0,
        origin="source",
        extraction_method="source-metadata",
        review_status="CANONICAL",
    )


def project_locations(
    record: CanonicalRecord,
    *,
    geocoder: Geocoder | None = None,
) -> list[LocationEntity]:
    """Project direct and inferred locations, optionally adding explicit geocoder results."""
    locations: list[LocationEntity] = []
    direct = _source_location(record)
    if direct:
        locations.append(direct)

    seen = {(item.origin, item.normalized_name) for item in locations}
    for event in _summary_event_candidates(record):
        value = event.get("location")
        if not isinstance(value, str) or not value.strip():
            continue
        name = value.strip()
        normalized = normalize_location_name(name)
        if ("inferred", normalized) in seen:
            continue
        confidence = event.get("confidence")
        inferred = LocationEntity(
            location_id=_stable_id("location", record.source_url, "inferred", normalized),
            name=name,
            normalized_name=normalized,
            country=record.source.country,
            source_url=record.source_url,
            evidence_ids=[str(item) for item in event.get("evidence", []) if item],
            confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
            origin="inferred",
            extraction_method="summary-event-candidate",
        )
        locations.append(inferred)
        seen.add(("inferred", normalized))

        if geocoder is None:
            continue
        result = geocoder.geocode(name)
        if result is None:
            continue
        locations.append(
            LocationEntity(
                location_id=_stable_id("location", record.source_url, "geocoded", normalized),
                name=name,
                normalized_name=result.normalized_name or normalized,
                latitude=result.latitude,
                longitude=result.longitude,
                country=result.country or record.source.country,
                region=result.region,
                source_url=record.source_url,
                evidence_ids=list(inferred.evidence_ids),
                confidence=result.confidence,
                origin="geocoded",
                extraction_method="geocoder",
                geocoder=result.provider,
                metadata={"input_location_id": inferred.location_id},
            )
        )
    return locations


def project_timeline_events(
    record: CanonicalRecord,
    *,
    locations: list[LocationEntity] | None = None,
) -> list[TimelineEvent]:
    """Convert provisional summary events to stable visualization records."""
    projected_locations = locations if locations is not None else project_locations(record)
    by_name: dict[str, list[str]] = {}
    for location in projected_locations:
        by_name.setdefault(normalize_location_name(location.name), []).append(location.location_id)

    entity_refs = [entity.entity_id for entity in record.analysis.entities]
    signifier_refs = [item.object_id for item in record.analysis.signifiers]
    events: list[TimelineEvent] = []
    for candidate in _summary_event_candidates(record):
        description = str(candidate.get("description") or "").strip()
        time_text = str(candidate.get("time") or "").strip()
        location_name = str(candidate.get("location") or "").strip()
        actors = [str(item) for item in candidate.get("actors", []) if item]
        evidence = [str(item) for item in candidate.get("evidence", []) if item]
        confidence = candidate.get("confidence")
        label = description or "event candidate"
        events.append(
            TimelineEvent(
                event_id=_stable_id(
                    "event", record.source_url, description, time_text, location_name
                ),
                label=label,
                description=description,
                time_text=time_text,
                source_url=record.source_url,
                location_ids=by_name.get(normalize_location_name(location_name), []),
                actors=actors,
                entity_refs=entity_refs,
                signifier_refs=signifier_refs,
                evidence_ids=evidence,
                confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
                extraction_method="summary-event-candidate",
            )
        )
    return events


def project_network_relations(record: CanonicalRecord) -> list[NetworkRelation]:
    """Project canonical discourse relations plus explicit record/actor links for graph views."""
    relations: list[NetworkRelation] = []
    for relation in (
        record.analysis.relations
        + record.analysis.antagonisms
        + record.analysis.actor_entity_relations
    ):
        relations.append(
            NetworkRelation(
                relation_id=relation.relation_id,
                source_ref=relation.source_ref,
                target_ref=relation.target_ref,
                relation_type=relation.relation_type,
                source_url=record.source_url,
                evidence_ids=list(relation.evidence_ids),
                review_status=relation.review_status,
                provenance=relation.provenance_id or "canonical-analysis",
            )
        )

    actor = record.source.author.strip()
    if actor:
        actor_ref = f"actor:{actor}"
        for entity in record.analysis.entities:
            relations.append(
                NetworkRelation(
                    relation_id=_stable_id("network", record.source_url, actor_ref, entity.entity_id),
                    source_ref=actor_ref,
                    target_ref=entity.entity_id,
                    relation_type="MENTIONS_ENTITY",
                    source_url=record.source_url,
                    evidence_ids=list(entity.evidence_ids),
                    review_status=entity.review_status,
                    provenance="canonical-record-projection",
                )
            )
        for signifier in record.analysis.signifiers:
            relations.append(
                NetworkRelation(
                    relation_id=_stable_id(
                        "network", record.source_url, actor_ref, signifier.object_id
                    ),
                    source_ref=actor_ref,
                    target_ref=signifier.object_id,
                    relation_type="USES_SIGNIFIER",
                    source_url=record.source_url,
                    evidence_ids=list(signifier.evidence_ids),
                    review_status=signifier.review_status,
                    provenance="canonical-record-projection",
                )
            )
    return relations


def build_visualization_projection(record: CanonicalRecord) -> dict[str, list[dict[str, Any]]]:
    """Storage-neutral payload shared by Visualization and optional Neo4j indexing."""
    locations = project_locations(record)
    return {
        "locations": [item.model_dump(mode="json") for item in locations],
        "events": [
            item.model_dump(mode="json")
            for item in project_timeline_events(record, locations=locations)
        ],
        "network_relations": [
            item.model_dump(mode="json") for item in project_network_relations(record)
        ],
    }
