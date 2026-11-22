"""Theory-neutral Social Network Analysis helpers for Phase 2.

NetworkX is the reference compatibility layer. The module computes conventional
network-science measures and deliberately does not rename them as theoretical
constructs such as "network power".
"""
from .graph import (
    CommunicationMode,
    CommunicatorType,
    SNAEdge,
    SNANode,
    build_graph,
    temporal_slices,
)
from .import_export import read_gexf, read_graphml, write_gexf, write_graphml
from .metrics import community_assignments, graph_metrics

__all__ = [
    "CommunicatorType",
    "CommunicationMode",
    "SNAEdge",
    "SNANode",
    "build_graph",
    "community_assignments",
    "graph_metrics",
    "read_gexf",
    "read_graphml",
    "temporal_slices",
    "write_gexf",
    "write_graphml",
]
