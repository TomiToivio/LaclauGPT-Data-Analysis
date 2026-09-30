"""Readable SNA graph construction and temporal slicing."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class CommunicatorType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    INSTITUTION = "institution"
    PLATFORM = "platform"
    LLM = "llm"
    AI_AGENT = "ai_agent"
    BOT = "bot"
    ALGORITHMIC_SYSTEM = "algorithmic_system"
    DEVICE = "device"
    UNKNOWN = "unknown"
    OTHER = "other"


class CommunicationMode(StrEnum):
    HUMAN_GENERATED = "human_generated"
    MACHINE_GENERATED = "machine_generated"
    MACHINE_MEDIATED = "machine_mediated"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class SNANode(BaseModel):
    node_id: str
    node_type: CommunicatorType = CommunicatorType.UNKNOWN
    label: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class SNAEdge(BaseModel):
    edge_id: str
    source: str
    target: str
    relation_type: str
    directed: bool = True
    weight: float = Field(default=1.0, ge=0)
    timestamp: datetime | None = None
    source_url: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    communication_mode: CommunicationMode = CommunicationMode.UNKNOWN
    attributes: dict[str, Any] = Field(default_factory=dict)


GraphKind = Literal["Graph", "DiGraph", "MultiGraph", "MultiDiGraph"]


def build_graph(
    nodes: Iterable[SNANode],
    edges: Iterable[SNAEdge],
    *,
    graph_kind: GraphKind = "MultiDiGraph",
):
    """Build a NetworkX graph while preserving deterministic ids and provenance."""
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("SNA requires the 'analysis' optional dependency") from exc

    graph_cls = {
        "Graph": nx.Graph,
        "DiGraph": nx.DiGraph,
        "MultiGraph": nx.MultiGraph,
        "MultiDiGraph": nx.MultiDiGraph,
    }[graph_kind]
    graph = graph_cls()
    graph.graph["laclaugpt_stage"] = "sna"
    graph.graph["interpretation_boundary"] = (
        "conventional network-science measures; no metric is a theoretical construct"
    )

    for node in nodes:
        graph.add_node(
            node.node_id,
            node_type=node.node_type.value,
            label=node.label or node.node_id,
            **node.attributes,
        )

    for edge in edges:
        attrs = {
            "edge_id": edge.edge_id,
            "relation_type": edge.relation_type,
            "weight": float(edge.weight),
            "timestamp": edge.timestamp.isoformat() if edge.timestamp else "",
            "source_url": edge.source_url or "",
            "evidence_ids": "|".join(edge.evidence_ids),
            "communication_mode": edge.communication_mode.value,
            **edge.attributes,
        }
        if graph.is_multigraph():
            graph.add_edge(edge.source, edge.target, key=edge.edge_id, **attrs)
        else:
            graph.add_edge(edge.source, edge.target, **attrs)
    return graph


def temporal_slices(
    edges: Iterable[SNAEdge],
    *,
    starts: Iterable[datetime],
    window_seconds: int,
) -> list[tuple[datetime, datetime, list[SNAEdge]]]:
    """Create explicit half-open temporal windows [start, end)."""
    from datetime import timedelta

    if window_seconds <= 0:
        raise ValueError("window_seconds must be > 0")
    rows = list(edges)
    result = []
    for start in starts:
        end = start + timedelta(seconds=window_seconds)
        result.append(
            (
                start,
                end,
                [edge for edge in rows if edge.timestamp is not None and start <= edge.timestamp < end],
            )
        )
    return result
