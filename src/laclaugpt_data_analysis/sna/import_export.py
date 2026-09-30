"""NetworkX-compatible GraphML/GEXF exchange for the SNA stage."""
from __future__ import annotations

from pathlib import Path


def write_graphml(graph, path: str | Path) -> Path:
    import networkx as nx

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, out)
    return out


def read_graphml(path: str | Path):
    import networkx as nx

    return nx.read_graphml(path)


def write_gexf(graph, path: str | Path) -> Path:
    import networkx as nx

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    nx.write_gexf(graph, out)
    return out


def read_gexf(path: str | Path):
    import networkx as nx

    return nx.read_gexf(path)
