from __future__ import annotations

from laclaugpt_data_analysis.dats_adapter import export_project, import_project


def test_complete_dats_adapter_preserves_hierarchy_review_notes_time_and_relations() -> None:
    payload = {
        "project_id": "p1",
        "documents": [{"id": "d1", "text": "AI changes institutions.", "language": "en"}],
        "codes": [
            {"id": "root", "label": "AI"},
            {"id": "child", "label": "change", "parent_id": "root"},
        ],
        "annotations": [
            {
                "id": "a1",
                "document_id": "d1",
                "code_id": "child",
                "start": 0,
                "end": 2,
                "producer_type": "model",
                "producer_id": "m1",
            }
        ],
        "notes": [
            {"id": "n1", "text": "research memo", "producer_type": "human", "producer_id": "r1"}
        ],
        "reviews": [
            {
                "id": "r1",
                "target_id": "dats-annotation:a1",
                "reviewer": "researcher",
                "decision": "REVISED",
                "reviewed_at": "2026-09-17T09:30:00Z",
                "corrections": {"code_id": "dats-code:root"},
            }
        ],
        "temporal_series": [
            {
                "id": "t1",
                "label": "AI mentions",
                "unit": "count",
                "points": [{"timestamp": "2026-09-17T00:00:00Z", "value": 2, "count": 2}],
            }
        ],
        "whiteboard_relations": [
            {"id": "w1", "source_ref": "root", "target_ref": "child", "relation_type": "linked"}
        ],
    }

    project = import_project(payload)
    assert project.codes[1].parent_id == "dats-code:root"
    assert project.annotations[0].code_id == "dats-code:child"
    assert project.notes[0].text == "research memo"
    assert project.reviews[0].decision == "REVISED"
    assert project.temporal_series[0].points[0].value == 2
    assert project.relations[0]["relation_type"] == "linked"

    exported = export_project(project)
    assert exported["codes"][1]["parent_id"] == "root"
    assert exported["annotations"][0]["code_id"] == "child"
    assert exported["annotations"][0]["provisional_ai"] is True
    assert exported["notes"][0]["id"] == "n1"
    assert exported["relations"][0]["external_ids"]["dats"] == "w1"
