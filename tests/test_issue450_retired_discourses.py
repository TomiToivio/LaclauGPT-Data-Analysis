from laclaugpt_data_analysis.canonical import CanonicalRecord


def test_retired_discourses_round_trip():
    for previous in ([], [{"label": "historical", "evidence_ids": ["e1"]}]):
        raw = {"source_url": "https://example.org/item", "analysis": {"discourses": previous}}
        record = CanonicalRecord.model_validate(raw)
        assert record.legacy.get("analysis.discourses", []) == previous
        assert "discourses" not in record.canonical_dict()["analysis"]
        assert raw["analysis"]["discourses"] == previous
        assert CanonicalRecord.model_validate_json(record.model_dump_json()) == record
