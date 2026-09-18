"""Portable cross-language exchange helpers.

Heavy libraries are imported lazily so ordinary LaclauGPT execution does not require
NetworkX, pandas or PyArrow. Exchange metadata is explicit because a graph or table
without construction semantics is not a scientifically interpretable result.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .interoperability import DiscourseStatement, GraphProjection


def actor_concept_projection(
    statements: Sequence[DiscourseStatement],
    *,
    projection_id: str = "dna-actor-concept-affiliation",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], GraphProjection]:
    """Build a descriptive actor-concept affiliation projection.

    This does not infer equivalence, nodal status, ideological formation, antagonism
    or hegemony. Those remain downstream interpretive claims requiring evidence and
    human review.
    """
    actors: dict[str, str] = {}
    concepts: dict[str, str] = {}
    counts: dict[tuple[str, str, str], int] = {}
    for statement in statements:
        actors[statement.actor_id] = statement.actor_label
        concepts[statement.concept_id] = statement.concept_label
        qualifier = statement.qualifier or "unspecified"
        key = (statement.actor_id, statement.concept_id, qualifier)
        counts[key] = counts.get(key, 0) + 1

    nodes = [
        {"id": node_id, "label": label, "kind": "actor"}
        for node_id, label in sorted(actors.items())
    ] + [
        {"id": node_id, "label": label, "kind": "concept"}
        for node_id, label in sorted(concepts.items())
    ]
    edges = [
        {
            "source": actor,
            "target": concept,
            "qualifier": qualifier,
            "weight": weight,
        }
        for (actor, concept, qualifier), weight in sorted(counts.items())
    ]
    projection = GraphProjection(
        projection_id=projection_id,
        graph_type="bipartite",
        node_semantics="actors and coded concepts",
        edge_semantics="coded DiscourseStatement incidence, separated by qualifier",
        weighting_method="statement count",
        projection_method="actor-concept affiliation",
        parameters={"qualifier_separated": True},
        source_statement_ids=[statement.statement_id for statement in statements],
        producer={"type": "tool", "id": "laclaugpt-data-analysis", "version": "1"},
    )
    return nodes, edges, projection


def _networkx_exchange_graph(
    *,
    nodes: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    projection: GraphProjection,
):
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Graph exchange requires the 'analysis' optional dependencies") from exc

    graph = nx.MultiDiGraph()
    projection_json = json.dumps(
        projection.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
    )
    graph.graph["laclaugpt_projection"] = projection_json
    # NetworkX GEXF only preserves a limited set of graph metadata fields.
    graph.graph["name"] = projection_json
    for node in nodes:
        payload = dict(node)
        node_id = str(payload.pop("id"))
        graph.add_node(node_id, **{key: _graph_scalar(value) for key, value in payload.items()})
    for edge in edges:
        payload = dict(edge)
        source = str(payload.pop("source"))
        target = str(payload.pop("target"))
        edge_id = payload.pop("id", None)
        attrs = {key: _graph_scalar(value) for key, value in payload.items()}
        if edge_id is not None:
            attrs["laclaugpt_edge_id"] = str(edge_id)
            graph.add_edge(source, target, key=str(edge_id), id=str(edge_id), **attrs)
        else:
            graph.add_edge(source, target, **attrs)
    return graph


def _read_networkx_exchange_graph(graph, format_name: str):
    raw_projection = graph.graph.get("laclaugpt_projection") or graph.graph.get("name")
    if not raw_projection:
        raise ValueError(f"{format_name} lacks laclaugpt_projection construction semantics")
    projection = GraphProjection.model_validate(json.loads(raw_projection))
    relation_edge_ids = {
        str(attrs.get("laclaugpt_edge_id"))
        for _, _, attrs in graph.edges(data=True)
        if attrs.get("laclaugpt_edge_id")
    }
    relation_edge_ids.update(
        str(node_id)
        for node_id, attrs in graph.nodes(data=True)
        if str(node_id).startswith(("rel-", "relation:")) and not attrs
    )
    nodes = [
        {"id": str(node_id), **dict(attrs)}
        for node_id, attrs in graph.nodes(data=True)
        if str(node_id) not in relation_edge_ids
    ]
    edges = []
    for source, target, attrs in graph.edges(data=True):
        payload = dict(attrs)
        canonical_id = payload.get("laclaugpt_edge_id") or payload.get("id")
        if canonical_id is not None:
            payload["id"] = str(canonical_id)
        if "type" not in payload:
            payload["type"] = payload.get("label") or payload.get("kind") or "UNSPECIFIED"
        edges.append({"source": str(source), "target": str(target), **payload})
    return nodes, edges, projection


def write_graphml(
    path: str | Path,
    *,
    nodes: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    projection: GraphProjection,
) -> None:
    """Write GraphML with projection semantics embedded as graph attributes."""
    graph = _networkx_exchange_graph(nodes=nodes, edges=edges, projection=projection)
    import networkx as nx

    nx.write_graphml(graph, Path(path))


def read_graphml(path: str | Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], GraphProjection]:
    """Read GraphML and require LaclauGPT construction semantics to be present."""
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("GraphML exchange requires the 'analysis' optional dependencies") from exc

    graph = nx.read_graphml(Path(path), force_multigraph=True)
    return _read_networkx_exchange_graph(graph, "GraphML")


def write_gexf(
    path: str | Path,
    *,
    nodes: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    projection: GraphProjection,
) -> None:
    """Write GEXF with stable node IDs and explicit projection semantics."""
    graph = _networkx_exchange_graph(nodes=nodes, edges=edges, projection=projection)
    import networkx as nx

    nx.write_gexf(graph, Path(path))


def read_gexf(path: str | Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], GraphProjection]:
    """Read GEXF and require LaclauGPT construction semantics to be present."""
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("GEXF exchange requires the 'analysis' optional dependencies") from exc

    graph = nx.read_gexf(Path(path))
    return _read_networkx_exchange_graph(graph, "GEXF")


def write_parquet_rows(
    path: str | Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    metadata: Mapping[str, Any],
) -> None:
    """Write typed Arrow/Parquet exchange with a JSON result manifest in metadata."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Parquet exchange requires the 'arrow' optional dependencies") from exc

    table = pa.Table.from_pylist([dict(row) for row in rows])
    schema_metadata = dict(table.schema.metadata or {})
    schema_metadata[b"laclaugpt_manifest"] = json.dumps(
        dict(metadata), ensure_ascii=False, sort_keys=True, default=str
    ).encode("utf-8")
    table = table.cast(table.schema.with_metadata(schema_metadata))
    pq.write_table(table, Path(path))


def read_parquet_rows(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read Arrow/Parquet rows and require the exchange manifest."""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Parquet exchange requires the 'arrow' optional dependencies") from exc

    table = pq.read_table(Path(path))
    raw = (table.schema.metadata or {}).get(b"laclaugpt_manifest")
    if not raw:
        raise ValueError("Parquet file lacks laclaugpt_manifest metadata")
    return table.to_pylist(), json.loads(raw.decode("utf-8"))


def _graph_scalar(value: Any) -> str | int | float | bool:
    if isinstance(value, (str, int, float, bool)):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
