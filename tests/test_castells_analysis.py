from datetime import UTC, datetime

from laclaugpt_data_analysis.analysis.castells import (
    NetworkEdge,
    NetworkNode,
    broker_scores,
    build_networkx_graph,
    edge_definition_sensitivity,
    geographic_flows,
    graph_measures,
    multiplex_layers,
    temporal_flows,
)
from laclaugpt_data_analysis.config import Settings


def _fixture():
    nodes = [
        NetworkNode("a", "actor"),
        NetworkNode("b", "actor"),
        NetworkNode("c", "actor"),
        NetworkNode("d", "actor"),
    ]
    t1 = datetime(2026, 9, 1, tzinfo=UTC)
    t2 = datetime(2026, 9, 2, tzinfo=UTC)
    edges = [
        NetworkEdge("a", "b", "mention", timestamp=t1, platform="x", source_url="https://x.example/1"),
        NetworkEdge("b", "c", "mention", timestamp=t2, platform="x", source_url="https://x.example/2"),
        NetworkEdge("c", "d", "semantic_similarity", observed=False, source_url="urn:test:3"),
    ]
    return nodes, edges


def test_castells_disabled_by_default() -> None:
    assert Settings().castells_enabled is False


def test_multiplex_layers_preserve_relation_types() -> None:
    _, edges = _fixture()
    layers = multiplex_layers(edges)
    assert len(layers["mention"]) == 2
    assert layers["semantic_similarity"][0].observed is False


def test_graph_measures_and_brokerage_are_descriptive() -> None:
    nodes, edges = _fixture()
    graph = build_networkx_graph(nodes, edges)
    measures = graph_measures(graph)
    assert measures["degree"]["b"] >= 2
    assert 0 <= measures["betweenness"]["b"] <= 1

    communities = {"a": "elite", "b": "elite", "c": "grassroots", "d": "grassroots"}
    scores = {score.node_id: score for score in broker_scores(graph, communities)}
    assert scores["b"].community_spanning_share > 0


def test_temporal_and_geographic_flows_keep_provenance() -> None:
    _, edges = _fixture()
    flows = temporal_flows(edges)
    assert flows[0].source_url == "https://x.example/1"
    assert flows[-1].timestamp is None

    geo = geographic_flows(edges, {"a": "Helsinki", "b": "Brussels", "c": "Nairobi"})
    assert geo[0]["source_urls"]
    assert all(row["target_place"] != "" for row in geo)


def test_edge_definition_sensitivity_separates_observed_and_inferred() -> None:
    _, edges = _fixture()
    summary = edge_definition_sensitivity({"all": edges, "observed": [e for e in edges if e.observed]})
    assert summary["all"]["inferred_edges"] == 1
    assert summary["observed"]["inferred_edges"] == 0
