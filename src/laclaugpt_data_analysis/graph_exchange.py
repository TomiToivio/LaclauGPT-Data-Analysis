"""Portable graph interchange for DNA/rDNA and other network backends."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .interoperability import GraphProjection


def statements_to_actor_concept_graph(statements, projection: GraphProjection):
    """Build a bipartite NetworkX graph without assigning Laclauian meaning.

    NetworkX is optional. The caller receives a graph whose graph-level metadata
    records the scientific construction semantics needed for later interpretation.
    """
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install the 'analysis' extra for NetworkX graph exchange") from exc

    graph = nx.Graph()
    graph.graph.update(
        {
            "projection_id": projection.projection_id,
            "graph_type": projection.graph_type,
            "node_semantics": projection.node_semantics,
            "edge_semantics": projection.edge_semantics,
            "weighting_method": projection.weighting_method,
            "projection_method": projection.projection_method,
            "temporal_scope_json": json.dumps(projection.temporal_scope, sort_keys=True),
            "parameters_json": json.dumps(projection.parameters, sort_keys=True),
            "source_statement_ids_json": json.dumps(
                projection.source_statement_ids, sort_keys=True
            ),
            "producer_json": json.dumps(projection.producer.model_dump(mode="json"), sort_keys=True),
            "provenance_id": projection.provenance_id or "",
            "interpretation_status": "DESCRIPTIVE_ONLY",
        }
    )
    for statement in statements:
        actor = f"actor:{statement.actor_id}"
        concept = f"concept:{statement.concept_id}"
        graph.add_node(actor, kind="actor", label=statement.actor_label)
        graph.add_node(concept, kind="concept", label=statement.concept_label)
        if graph.has_edge(actor, concept):
            graph[actor][concept]["weight"] += 1.0
            ids = json.loads(graph[actor][concept]["statement_ids_json"])
            ids.append(statement.statement_id)
            graph[actor][concept]["statement_ids_json"] = json.dumps(ids)
        else:
            graph.add_edge(
                actor,
                concept,
                weight=1.0,
                qualifier=statement.qualifier or "",
                statement_ids_json=json.dumps([statement.statement_id]),
            )
    return graph


def write_graphml(graph, path: str | Path) -> None:
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install the 'analysis' extra for GraphML exchange") from exc
    nx.write_graphml(graph, path)


def read_graphml(path: str | Path):
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install the 'analysis' extra for GraphML exchange") from exc
    graph = nx.read_graphml(path)
    if graph.graph.get("interpretation_status") != "DESCRIPTIVE_ONLY":
        raise ValueError("GraphML lacks LaclauGPT descriptive-layer marker")
    return graph


def write_node_edge_csv(graph, node_path: str | Path, edge_path: str | Path) -> None:
    import csv

    with open(node_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "kind", "label"])
        writer.writeheader()
        for node_id, attrs in graph.nodes(data=True):
            writer.writerow(
                {"id": node_id, "kind": attrs.get("kind", ""), "label": attrs.get("label", "")}
            )
    with open(edge_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source", "target", "weight", "qualifier", "statement_ids_json"],
        )
        writer.writeheader()
        for source, target, attrs in graph.edges(data=True):
            writer.writerow(
                {
                    "source": source,
                    "target": target,
                    "weight": attrs.get("weight", 1.0),
                    "qualifier": attrs.get("qualifier", ""),
                    "statement_ids_json": attrs.get("statement_ids_json", "[]"),
                }
            )


def portable_result_manifest(
    *,
    producer: str,
    version: str | None,
    run_id: str,
    source_record_ids: list[str],
    parameters: dict[str, Any],
    artifacts: list[dict[str, Any]],
    uncertainty: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cross-language JSON manifest for Python/R analytical artifacts."""
    return {
        "schema_version": "1.0.0",
        "producer": {"id": producer, "version": version},
        "run_id": run_id,
        "source_record_ids": source_record_ids,
        "parameters": parameters,
        "artifacts": artifacts,
        "uncertainty": uncertainty or {},
        "interpretation_status": "DESCRIPTIVE_ONLY",
    }
