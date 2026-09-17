"""Thin optional igraph/Leiden backend for descriptive network analysis."""
from __future__ import annotations

from typing import Any


def analyze_graph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    resolution_parameter: float = 1.0,
    seed: int = 42,
) -> dict[str, Any]:
    """Return descriptive graph measures and Leiden communities.

    Community membership is a structural result only. It must not be promoted to
    ideological formation, antagonism, nodal status or hegemony without a separate
    evidence-grounded interpretive stage and human review.
    """
    try:
        import igraph as ig
        import leidenalg
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install the 'analysis' extra for igraph/Leiden support") from exc

    ids = [str(node["id"]) for node in nodes]
    index = {node_id: idx for idx, node_id in enumerate(ids)}
    graph = ig.Graph(directed=False)
    graph.add_vertices(ids)
    graph.add_edges([(index[str(e["source"])], index[str(e["target"])]) for e in edges])
    weights = [float(e.get("weight", 1.0)) for e in edges]
    if weights:
        graph.es["weight"] = weights

    partition = leidenalg.find_partition(
        graph,
        leidenalg.RBConfigurationVertexPartition,
        weights="weight" if weights else None,
        resolution_parameter=resolution_parameter,
        seed=seed,
    )
    membership = {ids[i]: int(group) for i, group in enumerate(partition.membership)}
    degree = {ids[i]: float(value) for i, value in enumerate(graph.degree())}
    betweenness = {ids[i]: float(value) for i, value in enumerate(graph.betweenness())}

    return {
        "producer": {
            "id": "igraph+leidenalg",
            "igraph_version": getattr(ig, "__version__", None),
            "leidenalg_version": getattr(leidenalg, "__version__", None),
        },
        "parameters": {
            "resolution_parameter": resolution_parameter,
            "seed": seed,
            "directed": False,
            "weight_attribute": "weight" if weights else None,
        },
        "degree": degree,
        "betweenness": betweenness,
        "community_membership": membership,
        "interpretation_status": "DESCRIPTIVE_ONLY",
        "methodological_warning": (
            "Leiden communities are structural clusters, not Laclauian ideological formations."
        ),
    }
