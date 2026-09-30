from datetime import UTC, datetime

from laclaugpt_data_analysis.sna import (
    CommunicationMode,
    SNAEdge,
    SNANode,
    build_graph,
    community_assignments,
    graph_metrics,
    read_gexf,
    read_graphml,
    temporal_slices,
    write_gexf,
    write_graphml,
)


def fixture_graph():
    nodes = [
        SNANode(node_id="a", node_type="person"),
        SNANode(node_id="b", node_type="llm"),
        SNANode(node_id="c", node_type="platform"),
    ]
    edges = [
        SNAEdge(
            edge_id="e1",
            source="a",
            target="b",
            relation_type="message",
            communication_mode=CommunicationMode.HUMAN_GENERATED,
            timestamp=datetime(2026, 9, 30, 8, tzinfo=UTC),
        ),
        SNAEdge(
            edge_id="e2",
            source="b",
            target="c",
            relation_type="publish",
            communication_mode=CommunicationMode.MACHINE_GENERATED,
            weight=2,
            timestamp=datetime(2026, 9, 30, 9, tzinfo=UTC),
        ),
    ]
    return nodes, edges


def test_conventional_metrics_have_known_small_graph_values():
    nodes, edges = fixture_graph()
    graph = build_graph(nodes, edges, graph_kind="DiGraph")
    metrics = graph_metrics(graph)
    assert metrics["degree"] == {"a": 1, "b": 2, "c": 1}
    assert metrics["in_degree"] == {"a": 0, "b": 1, "c": 1}
    assert metrics["out_degree"] == {"a": 1, "b": 1, "c": 0}
    assert metrics["density"] == 1 / 3
    assert metrics["betweenness"]["b"] == 0.5
    assert "power" not in metrics
    assert community_assignments(graph)


def test_graphml_and_gexf_round_trip(tmp_path):
    nodes, edges = fixture_graph()
    graph = build_graph(nodes, edges, graph_kind="DiGraph")
    graphml = write_graphml(graph, tmp_path / "graph.graphml")
    gexf = write_gexf(graph, tmp_path / "graph.gexf")
    graphml_reloaded = read_graphml(graphml)
    gexf_reloaded = read_gexf(gexf)
    assert set(graphml_reloaded.nodes) == {"a", "b", "c"}
    assert set(gexf_reloaded.nodes) == {"a", "b", "c"}


def test_temporal_slices_preserve_machine_and_human_events():
    _, edges = fixture_graph()
    slices = temporal_slices(
        edges,
        starts=[datetime(2026, 9, 30, 8, tzinfo=UTC), datetime(2026, 9, 30, 9, tzinfo=UTC)],
        window_seconds=3600,
    )
    assert [edge.edge_id for edge in slices[0][2]] == ["e1"]
    assert [edge.edge_id for edge in slices[1][2]] == ["e2"]
