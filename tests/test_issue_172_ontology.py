from laclaugpt.laclaugpt_ontology import build_jsonld, export_discourse


def _sample():
    record = {"document_id": "doc-1"}
    discourse = {
        "generated_at": "2026-09-18T17:00:00+00:00",
        "model_metadata": {"model": "gemma4:12b"},
        "prompt_version": "phase0-test",
        "collective_subjects": [{"label": "OpenAI", "confidence": 0.9}],
        "signifiers": [
            {"label": "AI", "confidence": 0.8},
            {"label": "artificial intelligence", "confidence": 0.8},
        ],
        "articulations": [
            {
                "subject": "OpenAI",
                "object": "AGI",
                "confidence": 0.91,
                "evidence": "OpenAI articulates AGI as a frontier project.",
                "validated": True,
            }
        ],
        "chains_equivalence": [{"subject": "AI", "object": "progress"}],
        "chains_difference": [{"subject": "AI", "object": "human intelligence"}],
        "antagonisms": [{"subject": "labs", "object": "critics"}],
        "frontiers": [{"subject": "us", "object": "them"}],
        "affects": [{"subject": "speaker", "object": "fear"}],
    }
    return record, discourse


def test_exports_jsonld_and_turtle_with_provenance():
    record, discourse = _sample()
    exported = export_discourse(record, discourse)
    graph = exported["jsonld"]["@graph"]
    assertions = [node for node in graph if node.get("@type") == "lg:AnalysisAssertion"]
    assert assertions
    assert all("prov:wasGeneratedBy" in node for node in assertions)
    assert all("lg:sourceDocument" in node for node in assertions)
    assert "lg:AnalysisAssertion" in exported["turtle"]


def test_keeps_similar_signifiers_distinct():
    record, discourse = _sample()
    graph = build_jsonld(record, discourse)["@graph"]
    labels = {
        node.get("skos:prefLabel")
        for node in graph
        if node.get("@type") == "lg:Signifier"
    }
    assert "AI" in labels
    assert "artificial intelligence" in labels


def test_covers_phase0_relations_without_network_projection():
    record, discourse = _sample()
    graph = build_jsonld(record, discourse)["@graph"]
    relation_ids = {
        node["lg:relation"]["@id"]
        for node in graph
        if node.get("@type") == "lg:AnalysisAssertion"
    }
    assert "https://laclaugpt.org/ontology/articulates" in relation_ids
    assert "https://laclaugpt.org/ontology/equivalentTo" in relation_ids
    assert "https://laclaugpt.org/ontology/differentFrom" in relation_ids
    assert "https://laclaugpt.org/ontology/antagonisticTo" in relation_ids
    assert "https://laclaugpt.org/ontology/constructsFrontier" in relation_ids
    assert "https://laclaugpt.org/ontology/expressesAffect" in relation_ids


def test_validation_and_revision_metadata_are_preserved():
    record, discourse = _sample()
    discourse["articulations"].append(
        {
            "subject": "OpenAI",
            "object": "general intelligence",
            "validated": False,
            "correction_of": "https://laclaugpt.org/ontology/assertion/original",
        }
    )
    graph = build_jsonld(record, discourse)["@graph"]
    assertions = [node for node in graph if node.get("@type") == "lg:AnalysisAssertion"]
    revised = [node for node in assertions if "prov:wasRevisionOf" in node]
    assert revised
    assert revised[0]["lg:validated"] is False
    assert revised[0]["prov:wasRevisionOf"]["@id"].endswith("/original")
