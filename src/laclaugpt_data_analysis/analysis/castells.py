"""Experimental Castells / Network Society analysis helpers.

Measured graph properties stay separate from theoretical interpretation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NetworkNode:
    node_id: str
    node_type: str
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NetworkEdge:
    source: str
    target: str
    relation_type: str
    observed: bool = True
    weight: float = 1.0
    timestamp: datetime | None = None
    platform: str | None = None
    collection_id: str | None = None
    source_url: str | None = None
    evidence_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerScore:
    node_id: str
    betweenness: float
    community_spanning_share: float
    participation_coefficient: float


@dataclass(frozen=True)
class FlowEvent:
    source_node: str
    target_node: str
    relation_type: str
    timestamp: datetime | None
    platform: str | None
    source_url: str | None
    observed: bool


def multiplex_layers(edges: Iterable[NetworkEdge]) -> dict[str, list[NetworkEdge]]:
    """Group edges into independently analyzable relation layers."""
    layers: dict[str, list[NetworkEdge]] = defaultdict(list)
    for edge in edges:
        layers[edge.relation_type].append(edge)
    return dict(layers)


def temporal_flows(edges: Iterable[NetworkEdge]) -> list[FlowEvent]:
    """Return timestamp-aware communication events, preserving provenance."""
    rows = [
        FlowEvent(
            source_node=edge.source,
            target_node=edge.target,
            relation_type=edge.relation_type,
            timestamp=edge.timestamp,
            platform=edge.platform,
            source_url=edge.source_url,
            observed=edge.observed,
        )
        for edge in edges
    ]
    return sorted(rows, key=lambda row: (row.timestamp is None, row.timestamp or datetime.max))


def geographic_flows(
    edges: Iterable[NetworkEdge], node_locations: dict[str, str]
) -> list[dict[str, Any]]:
    """Materialize place-to-place flows without inventing missing locations."""
    counts: Counter[tuple[str, str, str]] = Counter()
    evidence: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for edge in edges:
        source_place = node_locations.get(edge.source)
        target_place = node_locations.get(edge.target)
        if not source_place or not target_place:
            continue
        key = (source_place, target_place, edge.relation_type)
        counts[key] += edge.weight
        if edge.source_url:
            evidence[key].append(edge.source_url)
    return [
        {
            "source_place": source,
            "target_place": target,
            "relation_type": relation,
            "weight": weight,
            "source_urls": sorted(set(evidence[(source, target, relation)])),
        }
        for (source, target, relation), weight in sorted(counts.items())
    ]


def build_networkx_graph(
    nodes: Iterable[NetworkNode], edges: Iterable[NetworkEdge], *, directed: bool = True
):
    """Build a provenance-rich NetworkX graph. NetworkX is an optional dependency."""
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - optional dependency guard
        raise RuntimeError("Install the 'analysis' extra to use NetworkX measures") from exc
    graph = nx.MultiDiGraph() if directed else nx.MultiGraph()
    for node in nodes:
        graph.add_node(node.node_id, node_type=node.node_type, label=node.label, **node.metadata)
    for index, edge in enumerate(edges):
        graph.add_edge(
            edge.source,
            edge.target,
            key=f"{edge.relation_type}:{index}",
            relation_type=edge.relation_type,
            observed=edge.observed,
            weight=edge.weight,
            timestamp=edge.timestamp.isoformat() if edge.timestamp else None,
            platform=edge.platform,
            collection_id=edge.collection_id,
            source_url=edge.source_url,
            evidence_ids=list(edge.evidence_ids),
            **edge.metadata,
        )
    return graph


def graph_measures(graph) -> dict[str, Any]:
    """Compute descriptive SNA measures without labelling them as power."""
    import networkx as nx

    simple = nx.DiGraph()
    for source, target, data in graph.edges(data=True):
        weight = float(data.get("weight", 1.0))
        if simple.has_edge(source, target):
            simple[source][target]["weight"] += weight
        else:
            simple.add_edge(source, target, weight=weight)
    simple.add_nodes_from(graph.nodes())
    undirected = simple.to_undirected()
    betweenness = nx.betweenness_centrality(simple, weight=None, normalized=True)
    pagerank = nx.pagerank(simple, weight="weight") if simple.number_of_nodes() else {}
    clustering = nx.clustering(undirected, weight="weight") if undirected.number_of_nodes() else {}
    core = nx.core_number(undirected) if undirected.number_of_edges() else {n: 0 for n in undirected}
    return {
        "degree": dict(simple.degree()),
        "in_degree": dict(simple.in_degree()),
        "out_degree": dict(simple.out_degree()),
        "betweenness": betweenness,
        "pagerank": pagerank,
        "clustering": clustering,
        "k_core": core,
        "components": [sorted(component) for component in nx.weakly_connected_components(simple)],
        "density": nx.density(simple),
    }


def broker_scores(graph, communities: dict[str, str]) -> list[BrokerScore]:
    """Estimate brokerage using betweenness plus community-spanning ties.

    These are measured structural indicators, not automatic evidence of Castellsian
    network power or switching power.
    """
    import networkx as nx

    simple = nx.Graph()
    simple.add_nodes_from(graph.nodes())
    simple.add_edges_from((u, v) for u, v in graph.edges())
    betweenness = nx.betweenness_centrality(simple, normalized=True)
    results: list[BrokerScore] = []
    for node in simple.nodes():
        neighbors = list(simple.neighbors(node))
        if not neighbors:
            results.append(BrokerScore(node, betweenness.get(node, 0.0), 0.0, 0.0))
            continue
        own = communities.get(node)
        spanning = sum(1 for neighbor in neighbors if communities.get(neighbor) != own) / len(neighbors)
        by_community = Counter(communities.get(neighbor, "unknown") for neighbor in neighbors)
        total = len(neighbors)
        participation = 1.0 - sum((count / total) ** 2 for count in by_community.values())
        results.append(BrokerScore(node, betweenness.get(node, 0.0), spanning, participation))
    return sorted(results, key=lambda item: (item.betweenness, item.participation_coefficient), reverse=True)


def edge_definition_sensitivity(edge_sets: dict[str, Iterable[NetworkEdge]]) -> dict[str, Any]:
    """Summarize how network size changes under different edge definitions."""
    result: dict[str, Any] = {}
    for name, edges in edge_sets.items():
        materialized = list(edges)
        nodes = {endpoint for edge in materialized for endpoint in (edge.source, edge.target)}
        result[name] = {
            "nodes": len(nodes),
            "edges": len(materialized),
            "observed_edges": sum(edge.observed for edge in materialized),
            "inferred_edges": sum(not edge.observed for edge in materialized),
        }
    return result
