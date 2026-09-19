"""Storage-neutral analytical knowledge graph for LaclauGPT.

The canonical record remains authoritative. This module builds an optional graph
projection that preserves semantic identity across RDF, local files, MongoDB,
ArangoDB, DNA and SNA workflows without changing Phase-0 execution.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, Sequence

from pydantic import Field

from .canonical import CanonicalRecord
from .interoperability import DiscourseStatement
from .models import Model
from .rdf import LACLAUGPT, PROV, stable_uri

KG_SCHEMA_VERSION = "1.0.0"
AssertionKind = Literal["empirical", "coded", "model-derived", "graph-statistical"]
Layer = Literal["source", "laclau", "dna", "sna", "cross-layer"]


class GraphProvenance(Model):
    source_id: str
    source_url: str | None = None
    run_id: str | None = None
    provenance_id: str | None = None
    method: str | None = None
    model: str | None = None
    config_id: str | None = None
    codebook_refs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    transformation: str | None = None


class GraphNode(Model):
    id: str
    uri: str
    kind: str
    layer: Layer
    label: str | None = None
    assertion_kind: AssertionKind = "coded"
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: GraphProvenance
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    snapshot_id: str | None = None


class GraphEdge(Model):
    id: str
    uri: str
    source: str
    target: str
    kind: str
    layer: Layer
    directed: bool = True
    weight: float | None = None
    assertion_kind: AssertionKind = "coded"
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: GraphProvenance
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    snapshot_id: str | None = None


class AnalyticalGraph(Model):
    schema_version: str = KG_SCHEMA_VERSION
    project_id: str
    base_uri: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def validate_references(self) -> None:
        node_ids = {node.id for node in self.nodes}
        missing = sorted(
            {ref for edge in self.edges for ref in (edge.source, edge.target) if ref not in node_ids}
        )
        if missing:
            raise ValueError(f"Graph edges reference missing nodes: {missing}")


class SNARelation(Model):
    relation_id: str
    source_actor_id: str
    target_actor_id: str
    relation_type: Literal[
        "reply", "mention", "repost", "share", "hyperlink", "co-occurrence", "follow", "membership"
    ]
    source_url: str
    timestamp: datetime | None = None
    directed: bool = True
    weight: float = Field(default=1.0, ge=0)
    platform: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    provenance_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class SNADerivedResult(Model):
    result_id: str
    actor_id: str | None = None
    community_id: str | None = None
    metric: Literal["centrality", "component", "community", "role", "position"]
    value: str | float | int
    source_relation_ids: list[str] = Field(default_factory=list)
    window_start: datetime | None = None
    window_end: datetime | None = None
    snapshot_id: str
    provenance_id: str | None = None
    method: str
    parameters: dict[str, Any] = Field(default_factory=dict)


def _edge_uri(base_uri: str, project_id: str, kind: str, edge_id: str) -> str:
    return stable_uri(base_uri, project_id, f"edge/{kind}", edge_id)


def canonical_actor_uri(base_uri: str, project_id: str, actor_id: str) -> str:
    """Shared actor identity for Laclau, DNA and SNA layers."""
    return stable_uri(base_uri, project_id, "actor", actor_id)


def canonical_concept_uri(base_uri: str, project_id: str, concept_id: str) -> str:
    return stable_uri(base_uri, project_id, "concept", concept_id)


def _prov(
    *,
    source_id: str,
    source_url: str | None,
    run_id: str | None,
    provenance_id: str | None,
    method: str | None,
    model: str | None = None,
    codebook_refs: Sequence[str] = (),
    evidence_ids: Sequence[str] = (),
    transformation: str | None = None,
) -> GraphProvenance:
    return GraphProvenance(
        source_id=source_id,
        source_url=source_url,
        run_id=run_id,
        provenance_id=provenance_id,
        method=method,
        model=model,
        codebook_refs=list(codebook_refs),
        evidence_ids=list(evidence_ids),
        transformation=transformation,
    )


def project_laclau_record(
    record: CanonicalRecord,
    *,
    project_id: str,
    base_uri: str = "https://data.example/laclaugpt",
    run_id: str | None = None,
) -> AnalyticalGraph:
    """Project current canonical Laclau analysis into the common graph contract."""
    run_key = run_id or f"laclau:{record.source_url}:{record.schema_version}"
    source_id = f"source:{record.source_url}"
    provenance_by_id = {item.provenance_id: item for item in record.provenance}
    graph = AnalyticalGraph(
        project_id=project_id,
        base_uri=base_uri,
        metadata={"projection": "laclau", "canonical_schema_version": record.schema_version},
    )
    graph.nodes.append(
        GraphNode(
            id=source_id,
            uri=stable_uri(base_uri, project_id, "source", record.source_url),
            kind="source",
            layer="source",
            label=record.content.title or record.source_url,
            assertion_kind="empirical",
            properties={
                "platform": record.source.platform,
                "language": record.content.language or record.source.language,
                "region": record.source.region if hasattr(record.source, "region") else None,
                "country": record.source.country,
                "created_at": record.source.created_at.isoformat() if record.source.created_at else None,
            },
            provenance=_prov(
                source_id=source_id,
                source_url=record.source_url,
                run_id=run_key,
                provenance_id=None,
                method="collection-source",
            ),
        )
    )

    object_groups = {
        "actor": record.analysis.entities,
        "theme": record.analysis.themes,
        "formation": record.analysis.formations,
        "signifier": record.analysis.signifiers,
        "nodal-point": record.analysis.nodal_points,
        "floating-signifier": record.analysis.floating_signifiers,
        "empty-signifier": record.analysis.empty_signifier_candidates,
        "discourse": record.analysis.discourses,
        "imaginary": record.analysis.imaginaries,
        "collective-subject": record.analysis.us,
        "other": record.analysis.them,
        "frontier": record.analysis.frontier,
        "affect": record.analysis.affects,
    }
    for kind, objects in object_groups.items():
        for obj in objects:
            object_id = getattr(obj, "entity_id", None) or getattr(obj, "object_id", None)
            label = getattr(obj, "label", None)
            prov_id = getattr(obj, "provenance_id", None)
            evidence_ids = list(getattr(obj, "evidence_ids", []))
            raw_prov = provenance_by_id.get(prov_id)
            node_uri = (
                canonical_actor_uri(base_uri, project_id, object_id)
                if kind == "actor"
                else canonical_concept_uri(base_uri, project_id, object_id)
            )
            graph.nodes.append(
                GraphNode(
                    id=object_id,
                    uri=node_uri,
                    kind=kind,
                    layer="laclau",
                    label=label,
                    assertion_kind="coded",
                    properties={
                        "review_status": getattr(obj, "review_status", "PROVISIONAL"),
                        "confidence": getattr(obj, "confidence", None),
                        "uncertainty": getattr(obj, "uncertainty", None),
                    },
                    provenance=_prov(
                        source_id=source_id,
                        source_url=record.source_url,
                        run_id=run_key,
                        provenance_id=prov_id,
                        method=raw_prov.method if raw_prov else "laclau-discourse-analysis",
                        model=raw_prov.model if raw_prov else None,
                        codebook_refs=record.analysis.codebook_refs,
                        evidence_ids=evidence_ids,
                        transformation="canonical-record-to-knowledge-graph",
                    ),
                )
            )

    known_nodes = {node.id for node in graph.nodes}
    relations = (
        list(record.analysis.relations)
        + list(record.analysis.antagonisms)
        + list(record.analysis.actor_entity_relations)
    )
    for relation in relations:
        for endpoint in (relation.source_ref, relation.target_ref):
            if endpoint not in known_nodes:
                graph.nodes.append(
                    GraphNode(
                        id=endpoint,
                        uri=canonical_concept_uri(base_uri, project_id, endpoint),
                        kind="reference",
                        layer="laclau",
                        assertion_kind="coded",
                        provenance=_prov(
                            source_id=source_id,
                            source_url=record.source_url,
                            run_id=run_key,
                            provenance_id=relation.provenance_id,
                            method="laclau-reference-placeholder",
                        ),
                    )
                )
                known_nodes.add(endpoint)
        raw_prov = provenance_by_id.get(relation.provenance_id)
        graph.edges.append(
            GraphEdge(
                id=relation.relation_id,
                uri=_edge_uri(base_uri, project_id, "laclau", relation.relation_id),
                source=relation.source_ref,
                target=relation.target_ref,
                kind=relation.relation_type,
                layer="laclau",
                assertion_kind="coded",
                properties={"review_status": relation.review_status},
                provenance=_prov(
                    source_id=source_id,
                    source_url=record.source_url,
                    run_id=run_key,
                    provenance_id=relation.provenance_id,
                    method=raw_prov.method if raw_prov else "laclau-discourse-analysis",
                    model=raw_prov.model if raw_prov else None,
                    codebook_refs=record.analysis.codebook_refs,
                    evidence_ids=relation.evidence_ids,
                    transformation="canonical-relation-to-knowledge-graph",
                ),
            )
        )

    for chain in list(record.analysis.equivalence_chains) + list(record.analysis.difference_chains):
        chain_node_id = f"chain:{chain.chain_id}"
        graph.nodes.append(
            GraphNode(
                id=chain_node_id,
                uri=stable_uri(base_uri, project_id, "chain", chain.chain_id),
                kind=f"{chain.chain_type}-chain",
                layer="laclau",
                assertion_kind="coded",
                properties={"review_status": chain.review_status},
                provenance=_prov(
                    source_id=source_id,
                    source_url=record.source_url,
                    run_id=run_key,
                    provenance_id=chain.provenance_id,
                    method="laclau-discourse-analysis",
                    evidence_ids=chain.evidence_ids,
                    transformation="relation-chain-projection",
                ),
            )
        )
        for index, member in enumerate(chain.member_refs):
            if member not in known_nodes:
                graph.nodes.append(
                    GraphNode(
                        id=member,
                        uri=canonical_concept_uri(base_uri, project_id, member),
                        kind="reference",
                        layer="laclau",
                        provenance=_prov(
                            source_id=source_id,
                            source_url=record.source_url,
                            run_id=run_key,
                            provenance_id=chain.provenance_id,
                            method="laclau-reference-placeholder",
                        ),
                    )
                )
                known_nodes.add(member)
            edge_id = f"{chain.chain_id}:{index}:{member}"
            graph.edges.append(
                GraphEdge(
                    id=edge_id,
                    uri=_edge_uri(base_uri, project_id, "chain-member", edge_id),
                    source=chain_node_id,
                    target=member,
                    kind="has-member",
                    layer="laclau",
                    directed=True,
                    assertion_kind="coded",
                    properties={"position": index, "chain_type": chain.chain_type},
                    provenance=_prov(
                        source_id=source_id,
                        source_url=record.source_url,
                        run_id=run_key,
                        provenance_id=chain.provenance_id,
                        method="laclau-discourse-analysis",
                        evidence_ids=chain.evidence_ids,
                        transformation="relation-chain-membership",
                    ),
                )
            )
    graph.validate_references()
    return graph


def project_dna(
    statements: Sequence[DiscourseStatement],
    *,
    project_id: str,
    base_uri: str = "https://data.example/laclaugpt",
    run_id: str | None = None,
) -> AnalyticalGraph:
    """Project DNA statements while reusing canonical actor identities."""
    graph = AnalyticalGraph(
        project_id=project_id,
        base_uri=base_uri,
        metadata={"projection": "dna", "phase": 2, "active": False},
    )
    seen: set[str] = set()
    for statement in statements:
        source_id = f"source:{statement.source_url}"
        if source_id not in seen:
            graph.nodes.append(
                GraphNode(
                    id=source_id,
                    uri=stable_uri(base_uri, project_id, "source", statement.source_url),
                    kind="source",
                    layer="source",
                    assertion_kind="empirical",
                    label=statement.source_document_id,
                    provenance=_prov(
                        source_id=source_id,
                        source_url=statement.source_url,
                        run_id=run_id,
                        provenance_id=statement.provenance_id,
                        method="dna-source",
                    ),
                )
            )
            seen.add(source_id)
        if statement.actor_id not in seen:
            graph.nodes.append(
                GraphNode(
                    id=statement.actor_id,
                    uri=canonical_actor_uri(base_uri, project_id, statement.actor_id),
                    kind="actor",
                    layer="dna",
                    label=statement.actor_label,
                    assertion_kind="coded",
                    provenance=_prov(
                        source_id=source_id,
                        source_url=statement.source_url,
                        run_id=run_id,
                        provenance_id=statement.provenance_id,
                        method="discourse-network-analysis",
                        evidence_ids=[statement.evidence_id] if statement.evidence_id else [],
                    ),
                )
            )
            seen.add(statement.actor_id)
        if statement.concept_id not in seen:
            graph.nodes.append(
                GraphNode(
                    id=statement.concept_id,
                    uri=canonical_concept_uri(base_uri, project_id, statement.concept_id),
                    kind="dna-concept",
                    layer="dna",
                    label=statement.concept_label,
                    assertion_kind="coded",
                    provenance=_prov(
                        source_id=source_id,
                        source_url=statement.source_url,
                        run_id=run_id,
                        provenance_id=statement.provenance_id,
                        method="discourse-network-analysis",
                        evidence_ids=[statement.evidence_id] if statement.evidence_id else [],
                    ),
                )
            )
            seen.add(statement.concept_id)
        graph.nodes.append(
            GraphNode(
                id=statement.statement_id,
                uri=stable_uri(base_uri, project_id, "statement", statement.statement_id),
                kind="statement",
                layer="dna",
                label=statement.evidence_text,
                assertion_kind="coded",
                properties={
                    "qualifier": statement.qualifier,
                    "confidence": statement.confidence,
                    "review_status": statement.review_status,
                    "timestamp": statement.timestamp.isoformat() if statement.timestamp else None,
                },
                provenance=_prov(
                    source_id=source_id,
                    source_url=statement.source_url,
                    run_id=run_id,
                    provenance_id=statement.provenance_id,
                    method="discourse-network-analysis",
                    evidence_ids=[statement.evidence_id] if statement.evidence_id else [],
                    transformation="dna-statement-projection",
                ),
                valid_from=statement.timestamp,
            )
        )
        for kind, src, dst in (
            ("actor-statement", statement.actor_id, statement.statement_id),
            ("statement-concept", statement.statement_id, statement.concept_id),
            ("statement-source", statement.statement_id, source_id),
        ):
            edge_id = f"{statement.statement_id}:{kind}"
            graph.edges.append(
                GraphEdge(
                    id=edge_id,
                    uri=_edge_uri(base_uri, project_id, "dna", edge_id),
                    source=src,
                    target=dst,
                    kind=kind,
                    layer="dna",
                    assertion_kind="coded",
                    properties={"qualifier": statement.qualifier},
                    provenance=_prov(
                        source_id=source_id,
                        source_url=statement.source_url,
                        run_id=run_id,
                        provenance_id=statement.provenance_id,
                        method="discourse-network-analysis",
                        evidence_ids=[statement.evidence_id] if statement.evidence_id else [],
                    ),
                    valid_from=statement.timestamp,
                )
            )
    graph.validate_references()
    return graph


def project_sna(
    relations: Sequence[SNARelation],
    derived: Sequence[SNADerivedResult] = (),
    *,
    project_id: str,
    base_uri: str = "https://data.example/laclaugpt",
    run_id: str | None = None,
) -> AnalyticalGraph:
    """Project empirical SNA relations plus snapshot-scoped derived results."""
    graph = AnalyticalGraph(
        project_id=project_id,
        base_uri=base_uri,
        metadata={"projection": "sna", "phase": 2, "active": False},
    )
    seen: set[str] = set()
    by_relation = {relation.relation_id: relation for relation in relations}
    for relation in relations:
        source_id = f"source:{relation.source_url}"
        if source_id not in seen:
            graph.nodes.append(
                GraphNode(
                    id=source_id,
                    uri=stable_uri(base_uri, project_id, "source", relation.source_url),
                    kind="source",
                    layer="source",
                    assertion_kind="empirical",
                    provenance=_prov(
                        source_id=source_id,
                        source_url=relation.source_url,
                        run_id=run_id,
                        provenance_id=relation.provenance_id,
                        method="social-network-source",
                    ),
                )
            )
            seen.add(source_id)
        for actor_id in (relation.source_actor_id, relation.target_actor_id):
            if actor_id not in seen:
                graph.nodes.append(
                    GraphNode(
                        id=actor_id,
                        uri=canonical_actor_uri(base_uri, project_id, actor_id),
                        kind="actor",
                        layer="sna",
                        assertion_kind="empirical",
                        provenance=_prov(
                            source_id=source_id,
                            source_url=relation.source_url,
                            run_id=run_id,
                            provenance_id=relation.provenance_id,
                            method="social-network-relation",
                        ),
                    )
                )
                seen.add(actor_id)
        graph.edges.append(
            GraphEdge(
                id=relation.relation_id,
                uri=_edge_uri(base_uri, project_id, "sna", relation.relation_id),
                source=relation.source_actor_id,
                target=relation.target_actor_id,
                kind=relation.relation_type,
                layer="sna",
                directed=relation.directed,
                weight=relation.weight,
                assertion_kind="empirical",
                properties={"platform": relation.platform, **relation.properties},
                provenance=_prov(
                    source_id=source_id,
                    source_url=relation.source_url,
                    run_id=run_id,
                    provenance_id=relation.provenance_id,
                    method="social-network-relation",
                    evidence_ids=relation.evidence_ids,
                ),
                valid_from=relation.timestamp,
            )
        )

    for result in derived:
        if result.actor_id:
            target_id = result.actor_id
            if target_id not in seen:
                graph.nodes.append(
                    GraphNode(
                        id=target_id,
                        uri=canonical_actor_uri(base_uri, project_id, target_id),
                        kind="actor",
                        layer="sna",
                        assertion_kind="empirical",
                        provenance=_prov(
                            source_id="derived:sna",
                            source_url=None,
                            run_id=run_id,
                            provenance_id=result.provenance_id,
                            method=result.method,
                        ),
                    )
                )
                seen.add(target_id)
        else:
            target_id = f"community:{result.community_id}"
            if target_id not in seen:
                graph.nodes.append(
                    GraphNode(
                        id=target_id,
                        uri=stable_uri(base_uri, project_id, "community", result.community_id or result.result_id),
                        kind="community",
                        layer="sna",
                        assertion_kind="graph-statistical",
                        provenance=_prov(
                            source_id="derived:sna",
                            source_url=None,
                            run_id=run_id,
                            provenance_id=result.provenance_id,
                            method=result.method,
                        ),
                        valid_from=result.window_start,
                        valid_to=result.window_end,
                        snapshot_id=result.snapshot_id,
                    )
                )
                seen.add(target_id)
        result_node = f"derived:{result.result_id}"
        relation_sources = [by_relation[rid].source_url for rid in result.source_relation_ids if rid in by_relation]
        graph.nodes.append(
            GraphNode(
                id=result_node,
                uri=stable_uri(base_uri, project_id, "sna-result", result.result_id),
                kind=f"derived-{result.metric}",
                layer="sna",
                assertion_kind="graph-statistical",
                properties={"value": result.value, "parameters": result.parameters},
                provenance=_prov(
                    source_id="derived:sna",
                    source_url=relation_sources[0] if relation_sources else None,
                    run_id=run_id,
                    provenance_id=result.provenance_id,
                    method=result.method,
                    transformation="graph-statistical-analysis",
                ),
                valid_from=result.window_start,
                valid_to=result.window_end,
                snapshot_id=result.snapshot_id,
            )
        )
        edge_id = f"{result.result_id}:describes"
        graph.edges.append(
            GraphEdge(
                id=edge_id,
                uri=_edge_uri(base_uri, project_id, "sna-derived", edge_id),
                source=result_node,
                target=target_id,
                kind="describes",
                layer="sna",
                assertion_kind="graph-statistical",
                properties={"metric": result.metric, "source_relation_ids": result.source_relation_ids},
                provenance=_prov(
                    source_id="derived:sna",
                    source_url=relation_sources[0] if relation_sources else None,
                    run_id=run_id,
                    provenance_id=result.provenance_id,
                    method=result.method,
                    transformation="graph-statistical-analysis",
                ),
                valid_from=result.window_start,
                valid_to=result.window_end,
                snapshot_id=result.snapshot_id,
            )
        )
    graph.validate_references()
    return graph


def merge_graphs(*graphs: AnalyticalGraph) -> AnalyticalGraph:
    if not graphs:
        raise ValueError("At least one graph is required")
    project_id, base_uri = graphs[0].project_id, graphs[0].base_uri
    if any(g.project_id != project_id or g.base_uri != base_uri for g in graphs):
        raise ValueError("Graphs must share project_id and base_uri")
    node_map: dict[str, GraphNode] = {}
    edge_map: dict[str, GraphEdge] = {}
    for graph in graphs:
        for node in graph.nodes:
            existing = node_map.get(node.id)
            if existing and existing.uri != node.uri:
                raise ValueError(f"Semantic identity conflict for node {node.id}")
            if not existing or existing.layer == "source":
                node_map[node.id] = node
        for edge in graph.edges:
            existing = edge_map.get(edge.id)
            if existing and existing.model_dump() != edge.model_dump():
                raise ValueError(f"Edge identity conflict for {edge.id}")
            edge_map[edge.id] = edge
    merged = AnalyticalGraph(
        project_id=project_id,
        base_uri=base_uri,
        nodes=list(node_map.values()),
        edges=list(edge_map.values()),
        metadata={"projection": "cross-layer", "components": [g.metadata.get("projection") for g in graphs]},
    )
    merged.validate_references()
    return merged


class GraphStore(Protocol):
    def write(self, graph: AnalyticalGraph) -> dict[str, Any]: ...

    def read(self, project_id: str) -> AnalyticalGraph: ...


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _node_row(node: GraphNode) -> dict[str, Any]:
    payload = node.model_dump(mode="json")
    payload["properties"] = _json(payload["properties"])
    payload["provenance"] = _json(payload["provenance"])
    return payload


def _edge_row(edge: GraphEdge) -> dict[str, Any]:
    payload = edge.model_dump(mode="json")
    payload["properties"] = _json(payload["properties"])
    payload["provenance"] = _json(payload["provenance"])
    return payload


class CSVGraphStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def write(self, graph: AnalyticalGraph) -> dict[str, Any]:
        self.directory.mkdir(parents=True, exist_ok=True)
        nodes_path, edges_path = self.directory / "nodes.csv", self.directory / "edges.csv"
        node_rows = [_node_row(node) for node in graph.nodes]
        edge_rows = [_edge_row(edge) for edge in graph.edges]
        for path, rows in ((nodes_path, node_rows), (edges_path, edge_rows)):
            fieldnames = list(rows[0]) if rows else []
            with path.open("w", encoding="utf-8", newline="") as handle:
                if fieldnames:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
        (self.directory / "manifest.json").write_text(
            _json(
                {
                    "schema_version": graph.schema_version,
                    "project_id": graph.project_id,
                    "base_uri": graph.base_uri,
                    "metadata": graph.metadata,
                }
            ),
            encoding="utf-8",
        )
        return {"backend": "csv", "nodes": len(graph.nodes), "edges": len(graph.edges)}

    def read(self, project_id: str) -> AnalyticalGraph:
        manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest["project_id"] != project_id:
            raise ValueError("Project mismatch")
        nodes = []
        edges = []
        with (self.directory / "nodes.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                row["properties"] = json.loads(row["properties"])
                row["provenance"] = json.loads(row["provenance"])
                for key in ("valid_from", "valid_to", "snapshot_id"):
                    row[key] = row[key] or None
                nodes.append(GraphNode.model_validate(row))
        with (self.directory / "edges.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                row["properties"] = json.loads(row["properties"])
                row["provenance"] = json.loads(row["provenance"])
                row["directed"] = row["directed"].lower() == "true"
                row["weight"] = float(row["weight"]) if row["weight"] else None
                for key in ("valid_from", "valid_to", "snapshot_id"):
                    row[key] = row[key] or None
                edges.append(GraphEdge.model_validate(row))
        return AnalyticalGraph(
            schema_version=manifest["schema_version"],
            project_id=manifest["project_id"],
            base_uri=manifest["base_uri"],
            nodes=nodes,
            edges=edges,
            metadata=manifest.get("metadata", {}),
        )


class SQLiteGraphStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def write(self, graph: AnalyticalGraph) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS kg_meta (
                    project_id TEXT PRIMARY KEY, schema_version TEXT NOT NULL,
                    base_uri TEXT NOT NULL, metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kg_nodes (
                    project_id TEXT NOT NULL, id TEXT NOT NULL, payload_json TEXT NOT NULL,
                    PRIMARY KEY (project_id, id)
                );
                CREATE TABLE IF NOT EXISTS kg_edges (
                    project_id TEXT NOT NULL, id TEXT NOT NULL, source TEXT NOT NULL,
                    target TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL,
                    PRIMARY KEY (project_id, id)
                );
                CREATE INDEX IF NOT EXISTS idx_kg_edges_source ON kg_edges(project_id, source);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_target ON kg_edges(project_id, target);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_kind ON kg_edges(project_id, kind);
                """
            )
            db.execute(
                "INSERT OR REPLACE INTO kg_meta VALUES (?, ?, ?, ?)",
                (graph.project_id, graph.schema_version, graph.base_uri, _json(graph.metadata)),
            )
            db.executemany(
                "INSERT OR REPLACE INTO kg_nodes VALUES (?, ?, ?)",
                [
                    (graph.project_id, node.id, _json(node.model_dump(mode="json")))
                    for node in graph.nodes
                ],
            )
            db.executemany(
                "INSERT OR REPLACE INTO kg_edges VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        graph.project_id,
                        edge.id,
                        edge.source,
                        edge.target,
                        edge.kind,
                        _json(edge.model_dump(mode="json")),
                    )
                    for edge in graph.edges
                ],
            )
        return {"backend": "sqlite", "nodes": len(graph.nodes), "edges": len(graph.edges)}

    def read(self, project_id: str) -> AnalyticalGraph:
        with sqlite3.connect(self.path) as db:
            meta = db.execute(
                "SELECT schema_version, base_uri, metadata_json FROM kg_meta WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if meta is None:
                raise KeyError(project_id)
            nodes = [
                GraphNode.model_validate(json.loads(row[0]))
                for row in db.execute(
                    "SELECT payload_json FROM kg_nodes WHERE project_id=? ORDER BY id", (project_id,)
                )
            ]
            edges = [
                GraphEdge.model_validate(json.loads(row[0]))
                for row in db.execute(
                    "SELECT payload_json FROM kg_edges WHERE project_id=? ORDER BY id", (project_id,)
                )
            ]
        return AnalyticalGraph(
            schema_version=meta[0],
            project_id=project_id,
            base_uri=meta[1],
            nodes=nodes,
            edges=edges,
            metadata=json.loads(meta[2]),
        )


class MongoGraphStore:
    """Thin adapter around a pymongo Database-like object."""

    def __init__(self, database: Any, *, prefix: str = "kg"):
        self.nodes = database[f"{prefix}_nodes"]
        self.edges = database[f"{prefix}_edges"]
        self.meta = database[f"{prefix}_meta"]

    def ensure_indexes(self) -> None:
        self.nodes.create_index([("project_id", 1), ("id", 1)], unique=True)
        self.nodes.create_index([("project_id", 1), ("kind", 1)])
        self.edges.create_index([("project_id", 1), ("id", 1)], unique=True)
        self.edges.create_index([("project_id", 1), ("kind", 1)])
        self.edges.create_index([("project_id", 1), ("source", 1)])
        self.edges.create_index([("project_id", 1), ("target", 1)])
        self.edges.create_index([("project_id", 1), ("valid_from", 1)])

    def write(self, graph: AnalyticalGraph) -> dict[str, Any]:
        self.ensure_indexes()
        self.meta.replace_one(
            {"project_id": graph.project_id},
            {
                "project_id": graph.project_id,
                "schema_version": graph.schema_version,
                "base_uri": graph.base_uri,
                "metadata": graph.metadata,
            },
            upsert=True,
        )
        for node in graph.nodes:
            payload = node.model_dump(mode="json")
            self.nodes.replace_one(
                {"project_id": graph.project_id, "id": node.id},
                {"project_id": graph.project_id, **payload},
                upsert=True,
            )
        for edge in graph.edges:
            payload = edge.model_dump(mode="json")
            self.edges.replace_one(
                {"project_id": graph.project_id, "id": edge.id},
                {"project_id": graph.project_id, **payload},
                upsert=True,
            )
        return {"backend": "mongodb", "nodes": len(graph.nodes), "edges": len(graph.edges)}


class ArangoGraphStore:
    """Optional adapter around an ArangoDB database-like object.

    The caller supplies an initialized database client; python-arango is not a
    baseline dependency.
    """

    def __init__(self, database: Any, *, vertex_collection: str = "kg_nodes", edge_collection: str = "kg_edges"):
        self.database = database
        self.vertex_collection = vertex_collection
        self.edge_collection = edge_collection

    @staticmethod
    def _key(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def write(self, graph: AnalyticalGraph) -> dict[str, Any]:
        vertices = (
            self.database.collection(self.vertex_collection)
            if self.database.has_collection(self.vertex_collection)
            else self.database.create_collection(self.vertex_collection)
        )
        edges = (
            self.database.collection(self.edge_collection)
            if self.database.has_collection(self.edge_collection)
            else self.database.create_collection(self.edge_collection, edge=True)
        )
        for node in graph.nodes:
            vertices.insert(
                {
                    "_key": self._key(f"{graph.project_id}:{node.id}"),
                    "project_id": graph.project_id,
                    **node.model_dump(mode="json"),
                },
                overwrite=True,
            )
        for edge in graph.edges:
            edges.insert(
                {
                    "_key": self._key(f"{graph.project_id}:{edge.id}"),
                    "_from": f"{self.vertex_collection}/{self._key(f'{graph.project_id}:{edge.source}')}",
                    "_to": f"{self.vertex_collection}/{self._key(f'{graph.project_id}:{edge.target}')}",
                    "project_id": graph.project_id,
                    **edge.model_dump(mode="json"),
                },
                overwrite=True,
            )
        return {"backend": "arangodb", "nodes": len(graph.nodes), "edges": len(graph.edges)}


def graph_to_rdf(graph: AnalyticalGraph):
    """Convert the common graph contract to an RDFLib Dataset."""
    try:
        import rdflib
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("RDF export requires the 'rdf' optional dependencies") from exc
    dataset = rdflib.Dataset()
    rdf = rdflib.namespace.RDF
    ns = rdflib.Namespace(LACLAUGPT)
    prov = rdflib.Namespace(PROV)
    dct = rdflib.namespace.DCTERMS
    for prefix, namespace in {"laclaugpt": ns, "prov": prov, "dcterms": dct}.items():
        dataset.bind(prefix, namespace)
    named = dataset.graph(
        rdflib.URIRef(stable_uri(graph.base_uri, graph.project_id, "graph", f"kg:{graph.schema_version}"))
    )
    by_id = {node.id: rdflib.URIRef(node.uri) for node in graph.nodes}
    for node in graph.nodes:
        subject = by_id[node.id]
        named.add((subject, rdf.type, rdflib.URIRef(f"{LACLAUGPT}{urllib.parse.quote(node.kind)}")))
        named.add((subject, dct.identifier, rdflib.Literal(node.id)))
        named.add((subject, ns.layer, rdflib.Literal(node.layer)))
        named.add((subject, ns.assertionKind, rdflib.Literal(node.assertion_kind)))
        if node.label:
            named.add((subject, rdflib.namespace.RDFS.label, rdflib.Literal(node.label)))
        if node.provenance.source_url:
            named.add((subject, prov.wasDerivedFrom, rdflib.URIRef(stable_uri(graph.base_uri, graph.project_id, "source", node.provenance.source_url))))
        if node.provenance.run_id:
            named.add((subject, prov.wasGeneratedBy, rdflib.URIRef(stable_uri(graph.base_uri, graph.project_id, "activity", node.provenance.run_id))))
    for edge in graph.edges:
        relation = rdflib.URIRef(edge.uri)
        named.add((relation, rdf.type, ns.GraphRelation))
        named.add((relation, dct.identifier, rdflib.Literal(edge.id)))
        named.add((relation, ns.source, by_id[edge.source]))
        named.add((relation, ns.target, by_id[edge.target]))
        named.add((relation, ns.relationType, rdflib.Literal(edge.kind)))
        named.add((relation, ns.layer, rdflib.Literal(edge.layer)))
        named.add((relation, ns.assertionKind, rdflib.Literal(edge.assertion_kind)))
        named.add((relation, ns.directed, rdflib.Literal(edge.directed)))
        if edge.weight is not None:
            named.add((relation, ns.weight, rdflib.Literal(edge.weight)))
        if edge.provenance.source_url:
            named.add((relation, prov.wasDerivedFrom, rdflib.URIRef(stable_uri(graph.base_uri, graph.project_id, "source", edge.provenance.source_url))))
        if edge.provenance.run_id:
            named.add((relation, prov.wasGeneratedBy, rdflib.URIRef(stable_uri(graph.base_uri, graph.project_id, "activity", edge.provenance.run_id))))
        for evidence_id in edge.provenance.evidence_ids:
            named.add((relation, ns.hasEvidence, rdflib.URIRef(stable_uri(graph.base_uri, graph.project_id, "evidence", evidence_id))))
    return dataset


def serialize_graph_rdf(graph: AnalyticalGraph, format_name: str = "json-ld") -> str:
    dataset = graph_to_rdf(graph)
    normalized = {"jsonld": "json-ld", "ttl": "turtle", "nq": "nquads"}.get(
        format_name.casefold(), format_name.casefold()
    )
    if normalized in {"nquads", "trig"}:
        return dataset.serialize(format=normalized)
    union = dataset.graph()
    for named in dataset.graphs():
        for triple in named:
            union.add(triple)
    return union.serialize(format=normalized)
