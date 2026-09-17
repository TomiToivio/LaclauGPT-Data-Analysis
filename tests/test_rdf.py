from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from laclaugpt_data_analysis.canonical import (
    CanonicalRecord,
    DiscourseObject,
    Entity,
    Evidence,
    Relation,
)
from laclaugpt_data_analysis.models import Provenance
from laclaugpt_data_analysis.plugin_pipeline import PluginContext, PluginRegistry
from laclaugpt_data_analysis.rdf import (
    FileRDFStore,
    RDFLibStore,
    RDFMaterializationPlugin,
    SPARQLStore,
    graphrag_enabled,
    import_profile_dataset,
    materialize_record,
    rdf_config,
    retrieve_subgraph,
    run_optional_rdf_postprocess,
    serialize_dataset,
    stable_uri,
    validate_dataset,
)


def fixture() -> CanonicalRecord:
    record = CanonicalRecord(
        source_url="https://example.org/source/ääni",
        source_native_ids={"synthetic": "doc-1"},
        raw_capture={"payload": {"secret": "DO_NOT_PUBLISH_RAW"}},
        source={
            "platform": "synthetic",
            "author": "Ada Example",
            "language": "fi",
            "created_at": datetime(2026, 9, 17, tzinfo=UTC),
        },
        content={"title": "Vapaus ja tekoäly", "text": "Ada yhdistää vapauden avoimuuteen.", "language": "fi"},
        legacy={"private_note": "DO_NOT_PUBLISH_NOTE"},
    )
    provenance = Provenance(
        provenance_id="prov-1",
        method="laclau-discourse-analysis",
        model="gemma4:test",
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
    )
    record.provenance.append(provenance)
    record.evidence.append(
        Evidence(
            evidence_id="e-1",
            kind="text_span",
            source_url=record.source_url,
            quote="vapauden avoimuuteen",
            start_offset=14,
            end_offset=34,
            provenance_id="prov-1",
        )
    )
    record.analysis.entities.append(
        Entity(
            entity_id="person-ada",
            label="Ada Example",
            entity_type="person",
            provenance_id="prov-1",
            evidence_ids=["e-1"],
        )
    )
    record.analysis.signifiers.extend(
        [
            DiscourseObject(
                object_id="freedom",
                label="vapaus",
                kind="signifier",
                evidence_ids=["e-1"],
                confidence=0.91,
                provenance_id="prov-1",
                metadata={"labels": {"en": "freedom", "pl": "wolność"}},
            ),
            DiscourseObject(
                object_id="openness",
                label="avoimuus",
                kind="signifier",
                evidence_ids=["e-1"],
                confidence=0.87,
                provenance_id="prov-1",
            ),
        ]
    )
    record.analysis.nodal_points.append(
        DiscourseObject(
            object_id="freedom-nodal",
            label="vapaus",
            kind="nodal_point",
            evidence_ids=["e-1"],
            confidence=0.8,
            provenance_id="prov-1",
        )
    )
    record.analysis.relations.append(
        Relation(
            relation_id="a-1",
            relation_type="articulation",
            source_ref="freedom",
            target_ref="openness",
            evidence_ids=["e-1"],
            provenance_id="prov-1",
            review_status="PROVISIONAL",
        )
    )
    return record


def enabled_config(**rdf_overrides):
    rdf = {
        "enabled": True,
        "required": False,
        "formats": ["json-ld", "turtle", "nquads"],
        "store": {"backend": "file", "path": None},
        "validation": {"shacl": True},
        "graphrag": {"enabled": False, "max_nodes": 20, "max_edges": 30},
    }
    rdf.update(rdf_overrides)
    return {"project_id": "AI26", "analysis": {"rdf": rdf}}


def test_rdf_omitted_and_disabled_are_noops_without_importing_rdflib(monkeypatch):
    record = fixture()
    import laclaugpt_data_analysis.rdf as rdf_module

    monkeypatch.setattr(rdf_module, "_require_rdflib", lambda: (_ for _ in ()).throw(AssertionError("must not import RDF")))
    assert rdf_config({}).enabled is False
    assert run_optional_rdf_postprocess(record, project_config={}) is record
    assert run_optional_rdf_postprocess(record, project_config={"analysis": {"rdf": {"enabled": False}}}) is record
    assert "rdf" not in record.analysis.plugin_results


def test_graphrag_requires_both_feature_flags():
    assert graphrag_enabled({"analysis": {"rdf": {"enabled": False, "graphrag": {"enabled": True}}}}) is False
    assert graphrag_enabled({"analysis": {"rdf": {"enabled": True, "graphrag": {"enabled": False}}}}) is False
    assert graphrag_enabled({"analysis": {"rdf": {"enabled": True, "graphrag": {"enabled": True}}}}) is True


def test_deterministic_project_scoped_uri():
    left = stable_uri("https://data.example/laclaugpt", "AI26", "source", "https://example.org/x")
    right = stable_uri("https://data.example/laclaugpt", "AI26", "source", "https://example.org/x")
    other = stable_uri("https://data.example/laclaugpt", "EP24", "source", "https://example.org/x")
    assert left == right
    assert "/AI26/source/" in left
    assert left != other


def test_materialization_preserves_source_evidence_provenance_and_articulation():
    record = fixture()
    dataset = materialize_record(record, project_id="AI26")
    report = validate_dataset(dataset)
    assert report.conforms is True
    nquads = serialize_dataset(dataset, "nquads")
    turtle = serialize_dataset(dataset, "turtle")
    jsonld = serialize_dataset(dataset, "json-ld")
    assert record.source_url in nquads
    assert "vapauden avoimuuteen" in turtle
    assert "https://w3id.org/laclaugpt/Articulation" in nquads
    assert "http://www.w3.org/ns/prov#wasGeneratedBy" in nquads
    assert "http://www.w3.org/ns/oa#TextPositionSelector" in nquads
    assert json.loads(jsonld)
    assert "DO_NOT_PUBLISH_RAW" not in nquads
    assert "DO_NOT_PUBLISH_NOTE" not in nquads


def test_multilingual_skos_label_has_language_tag():
    ttl = serialize_dataset(materialize_record(fixture(), project_id="AI26"), "turtle")
    assert '"vapaus"@fi' in ttl


def test_profile_round_trip_recovers_source_and_relation_semantics():
    record = fixture()
    imported = import_profile_dataset(materialize_record(record, project_id="AI26"))
    source = next(item for item in imported if item["kind"] == "source")
    relation = next(item for item in imported if item["kind"] == "articulation")
    assert source["source_url"] == record.source_url
    assert relation["id"] == "a-1"
    assert relation["relation_type"] == "articulation"
    assert relation["review_state"] == "PROVISIONAL"
    assert len(relation["endpoints"]) == 2
    assert relation["generated_by"]
    assert relation["evidence"]


def test_file_and_rdflib_stores_are_offline(tmp_path):
    dataset = materialize_record(fixture(), project_id="AI26")
    file_store = FileRDFStore(tmp_path / "fixture.ttl")
    result = file_store.add(dataset)
    assert result["ok"] is True
    assert "Articulation" in (tmp_path / "fixture.ttl").read_text(encoding="utf-8")

    local = RDFLibStore()
    added = local.add(dataset)
    assert added["triples"] > 0
    assert "Articulation" in local.export("turtle")


def test_mocked_sparql_adapter_applies_limit(monkeypatch):
    store = SPARQLStore(query_endpoint="https://rdf.invalid/query")
    captured = {}

    def fake_request(url, data, content_type, accept):
        captured.update(url=url, body=data.decode(), content_type=content_type, accept=accept)
        return b'{"head":{},"results":{"bindings":[]}}'

    monkeypatch.setattr(store, "_request", fake_request)
    result = store.query("SELECT * WHERE { ?s ?p ?o }", limits={"limit": 7})
    assert result["results"]["bindings"] == []
    assert "LIMIT+7" in captured["body"]


def test_bounded_project_scoped_graphrag_returns_audit_provenance():
    dataset = materialize_record(fixture(), project_id="AI26")
    context = retrieve_subgraph(dataset, project_id="AI26", seed="freedom", max_nodes=6, max_edges=5)
    assert context.provenance["project_id"] == "AI26"
    assert context.provenance["max_edges"] == 5
    assert len(context.graph_paths) <= 5
    assert fixture().source_url in context.source_ids
    assert retrieve_subgraph(dataset, project_id="EP24", seed="freedom").text == ""


def test_enabled_postprocess_records_projection_and_serializations():
    record = run_optional_rdf_postprocess(fixture(), project_config=enabled_config())
    result = record.analysis.plugin_results["rdf"]
    assert result["project_id"] == "AI26"
    assert result["validation"]["conforms"] is True
    assert result["triple_count"] > 0
    assert set(result["serializations"]) == {"json-ld", "turtle", "nquads"}
    assert "rdf" not in record.analysis.plugin_failures


def test_optional_failure_isolated_but_required_failure_raises(monkeypatch):
    import laclaugpt_data_analysis.rdf as rdf_module

    monkeypatch.setattr(rdf_module, "materialize_record", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("synthetic failure")))
    optional = run_optional_rdf_postprocess(fixture(), project_config=enabled_config(required=False))
    assert optional.analysis.plugin_failures["rdf"]["error"] == "RuntimeError"
    assert optional.analysis.plugin_failures["rdf"]["required"] is False

    with pytest.raises(RuntimeError, match="synthetic failure"):
        run_optional_rdf_postprocess(fixture(), project_config=enabled_config(required=True))


def test_generic_plugin_runtime_contract():
    plugin = RDFMaterializationPlugin()
    registry = PluginRegistry()
    registry.register(plugin)
    assert "rdf_materialization" in registry.names()
    output = plugin.process(
        fixture(),
        PluginContext(project_id="AI26"),
        {
            "enabled": True,
            "formats": ["turtle"],
            "store": {"backend": "file", "path": None},
            "validation": {"shacl": True},
        },
    )
    assert output["project_id"] == "AI26"
    assert "turtle" in output["serializations"]
