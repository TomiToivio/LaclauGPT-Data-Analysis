from laclaugpt_data_analysis.canonical import CanonicalRecord, DiscourseObject, Entity, Relation
from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.deployment import render_cron
from laclaugpt_data_analysis.derived_structures import (
    GeocodeResult,
    build_visualization_projection,
    project_locations,
    project_network_relations,
    project_timeline_events,
)


class FakeGeocoder:
    def geocode(self, name: str):
        assert name == "Helsinki"
        return GeocodeResult(
            latitude=60.1699,
            longitude=24.9384,
            normalized_name="helsinki",
            country="FI",
            region="Uusimaa",
            confidence=0.99,
            provider="fake-geocoder",
        )


def record() -> CanonicalRecord:
    item = CanonicalRecord(source_url="https://example.org/post/1")
    item.source.author = "research-actor"
    item.source.country = "FI"
    item.source.platform = "bluesky"
    item.source.raw_metadata.update(
        {
            "collection_id": "AI26",
            "arena": "elites",
            "location": "Espoo",
            "lat": 60.2055,
            "lon": 24.6559,
        }
    )
    item.intermediate.stage_outputs["summary_preanalysis"] = [
        {
            "proposal": {
                "event_candidates": [
                    {
                        "description": "AI policy meeting",
                        "time": "2026-09-16",
                        "location": "Helsinki",
                        "actors": ["research-actor", "ministry"],
                        "evidence": ["evidence:1"],
                        "confidence": 0.8,
                    }
                ]
            }
        }
    ]
    item.analysis.entities = [
        Entity(entity_id="entity:ministry", label="Ministry", evidence_ids=["evidence:1"])
    ]
    item.analysis.signifiers = [
        DiscourseObject(
            object_id="signifier:agi",
            label="AGI",
            kind="signifier",
            evidence_ids=["evidence:1"],
            confidence=0.7,
        )
    ]
    item.analysis.relations = [
        Relation(
            relation_id="relation:1",
            relation_type="articulation",
            source_ref="AGI",
            target_ref="progress",
            evidence_ids=["evidence:1"],
        )
    ]
    return item


def test_source_inferred_and_geocoded_locations_stay_distinct():
    locations = project_locations(record(), geocoder=FakeGeocoder())
    assert [item.origin for item in locations] == ["source", "inferred", "geocoded"]
    assert locations[0].name == "Espoo"
    assert locations[0].review_status == "CANONICAL"
    assert locations[1].latitude is None
    assert locations[2].latitude == 60.1699
    assert locations[2].geocoder == "fake-geocoder"
    assert locations[2].metadata["input_location_id"] == locations[1].location_id


def test_timeline_event_keeps_source_evidence_and_visualization_refs():
    item = record()
    locations = project_locations(item)
    events = project_timeline_events(item, locations=locations)
    assert len(events) == 1
    event = events[0]
    assert event.source_url == item.source_url
    assert event.evidence_ids == ["evidence:1"]
    assert event.actors == ["research-actor", "ministry"]
    assert event.entity_refs == ["entity:ministry"]
    assert event.signifier_refs == ["signifier:agi"]
    assert event.location_ids


def test_network_projection_uses_canonical_discourse_semantics():
    relations = project_network_relations(record())
    relation_types = {item.relation_type for item in relations}
    assert "articulation" in relation_types
    assert "MENTIONS_ENTITY" in relation_types
    assert "USES_SIGNIFIER" in relation_types
    assert all(item.source_url == "https://example.org/post/1" for item in relations)
    assert all(item.provenance for item in relations)


def test_visualization_projection_is_storage_neutral_and_rebuildable():
    first = build_visualization_projection(record())
    second = build_visualization_projection(record())
    assert first == second
    assert set(first) == {"locations", "events", "network_relations"}
    assert first["events"][0]["event_id"].startswith("event:")


def test_local_analysis_configuration_requires_no_remote_services():
    settings = Settings()
    assert settings.remote_enabled is False
    assert settings.rag_enabled is False
    cron = render_cron("python -m laclaugpt_data_analysis.cli run")
    assert "flock -n" in cron
    assert "Mongo" not in cron
    assert "Redis" not in cron
