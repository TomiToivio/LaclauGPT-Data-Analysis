"""Conventional descriptive SNA measures.

These values are measurements of a graph representation. They must not be
automatically relabelled as Castellsian programming, switching, gatekeeping,
network power, ideology, influence, or causality.
"""
from __future__ import annotations

from typing import Any


def _simple_weighted(graph):
    import networkx as nx

    simple = nx.DiGraph() if graph.is_directed() else nx.Graph()
    simple.add_nodes_from(graph.nodes(data=True))
    for source, target, data in graph.edges(data=True):
        weight = float(data.get("weight", 1.0))
        if simple.has_edge(source, target):
            simple[source][target]["weight"] += weight
        else:
            simple.add_edge(source, target, weight=weight)
    return simple


def graph_metrics(graph) -> dict[str, Any]:
    """Compute a small deterministic set of standard network-science measures."""
    import networkx as nx

    simple = _simple_weighted(graph)
    undirected = simple.to_undirected()

    result: dict[str, Any] = {
        "degree": dict(simple.degree()),
        "weighted_degree": dict(simple.degree(weight="weight")),
        "density": nx.density(simple),
        "betweenness": nx.betweenness_centrality(simple, normalized=True),
        "closeness": nx.closeness_centrality(simple),
        "clustering": nx.clustering(undirected, weight="weight"),
    }
    if simple.is_directed():
        result["in_degree"] = dict(simple.in_degree())
        result["out_degree"] = dict(simple.out_degree())
        result["components"] = [
            sorted(component) for component in nx.weakly_connected_components(simple)
        ]
        result["pagerank"] = nx.pagerank(simple, weight="weight") if len(simple) else {}
    else:
        result["components"] = [
            sorted(component) for component in nx.connected_components(simple)
        ]
        result["pagerank"] = nx.pagerank(simple, weight="weight") if len(simple) else {}

    if len(simple) and simple.number_of_edges():
        try:
            result["eigenvector"] = nx.eigenvector_centrality_numpy(simple, weight="weight")
        except Exception:
            result["eigenvector"] = None
    else:
        result["eigenvector"] = {node: 0.0 for node in simple}

    result["interpretation"] = (
        "descriptive graph statistics only; theoretical interpretation requires "
        "separate evidence and argument"
    )
    return result


def community_assignments(graph) -> dict[str, int]:
    """Return deterministic greedy-modularity communities on the undirected graph."""
    import networkx as nx

    undirected = _simple_weighted(graph).to_undirected()
    if undirected.number_of_edges() == 0:
        return {node: index for index, node in enumerate(sorted(undirected), start=1)}

    communities = nx.algorithms.community.greedy_modularity_communities(
        undirected, weight="weight"
    )
    result: dict[str, int] = {}
    for community_id, members in enumerate(
        sorted((sorted(group) for group in communities), key=lambda group: group[0]),
        start=1,
    ):
        for node in members:
            result[node] = community_id
    return result
