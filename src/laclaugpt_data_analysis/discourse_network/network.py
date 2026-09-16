"""Optional descriptive Discourse Network Analysis projections.

Network structure is descriptive evidence, not a shortcut to Laclaudian theoretical
claims. Empty signifiers, nodal points, equivalence and antagonism require separate
interpretation and validation.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from .models import DiscourseStatement, Stance


def actor_concept_matrix(
    statements: Iterable[DiscourseStatement],
    *,
    confidence_weighted: bool = False,
) -> dict[str, dict[str, float]]:
    """Build a sparse actor -> concept signed matrix from raw statement events."""
    matrix: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for statement in statements:
        if statement.abstained:
            continue
        value = statement.signed_value
        if confidence_weighted and statement.confidence is not None:
            value *= statement.confidence
        matrix[statement.actor_id][statement.concept_id] += value
    return {actor: dict(concepts) for actor, concepts in matrix.items()}


def actor_projection(
    statements: Iterable[DiscourseStatement],
    *,
    conflict: bool = False,
    min_shared: int = 1,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Project actor-concept statements into actor congruence or conflict edges."""
    matrix = actor_concept_matrix(statements)
    actors = sorted(matrix)
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for i, left in enumerate(actors):
        for right in actors[i + 1 :]:
            shared = sorted(set(matrix[left]) & set(matrix[right]))
            matches: list[str] = []
            score = 0.0
            for concept in shared:
                lv, rv = matrix[left][concept], matrix[right][concept]
                if lv == 0 or rv == 0:
                    continue
                relation_is_conflict = (lv > 0) != (rv > 0)
                if relation_is_conflict == conflict:
                    matches.append(concept)
                    score += min(abs(lv), abs(rv))
            if len(matches) >= min_shared:
                edges[(left, right)] = {
                    "weight": score,
                    "shared_concepts": matches,
                    "kind": "conflict" if conflict else "congruence",
                }
    return edges


def concept_projection(
    statements: Iterable[DiscourseStatement],
    *,
    conflict: bool = False,
    min_shared: int = 1,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Project actor-concept statements into concept congruence or conflict edges."""
    by_concept: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for statement in statements:
        if statement.abstained:
            continue
        by_concept[statement.concept_id][statement.actor_id] += statement.signed_value
    concepts = sorted(by_concept)
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for i, left in enumerate(concepts):
        for right in concepts[i + 1 :]:
            actors = sorted(set(by_concept[left]) & set(by_concept[right]))
            matches: list[str] = []
            score = 0.0
            for actor in actors:
                lv, rv = by_concept[left][actor], by_concept[right][actor]
                if lv == 0 or rv == 0:
                    continue
                relation_is_conflict = (lv > 0) != (rv > 0)
                if relation_is_conflict == conflict:
                    matches.append(actor)
                    score += min(abs(lv), abs(rv))
            if len(matches) >= min_shared:
                edges[(left, right)] = {
                    "weight": score,
                    "shared_actors": matches,
                    "kind": "conflict" if conflict else "congruence",
                }
    return edges


def fixed_windows(
    statements: Iterable[DiscourseStatement],
    *,
    days: int = 7,
) -> list[tuple[datetime, datetime, list[DiscourseStatement]]]:
    """Split timestamped statements into reproducible fixed UTC-like day windows."""
    if days < 1:
        raise ValueError("days must be >= 1")
    rows = sorted((s for s in statements if s.timestamp is not None), key=lambda s: s.timestamp)
    if not rows:
        return []
    start = rows[0].timestamp
    assert start is not None
    start = datetime(start.year, start.month, start.day, tzinfo=start.tzinfo)
    width = timedelta(days=days)
    buckets: list[tuple[datetime, datetime, list[DiscourseStatement]]] = []
    cursor = start
    final = rows[-1].timestamp
    assert final is not None
    while cursor <= final:
        end = cursor + width
        bucket = [s for s in rows if s.timestamp is not None and cursor <= s.timestamp < end]
        buckets.append((cursor, end, bucket))
        cursor = end
    return buckets


def community_assignments(
    statements: Iterable[DiscourseStatement],
    *,
    min_shared: int = 1,
) -> list[dict[str, Any]]:
    """Return descriptive communities from actor congruence, never ideology labels."""
    rows = list(statements)
    actors = sorted({s.actor_id for s in rows if not s.abstained})
    try:
        import networkx as nx
    except ImportError:
        return [{"actor_id": actor, "community": index + 1, "method": "singleton-no-networkx"} for index, actor in enumerate(actors)]

    graph = nx.Graph()
    graph.add_nodes_from(actors)
    for (left, right), data in actor_projection(rows, min_shared=min_shared).items():
        graph.add_edge(left, right, weight=float(data["weight"]))
    if graph.number_of_edges() == 0:
        return [{"actor_id": actor, "community": index + 1, "method": "singleton"} for index, actor in enumerate(actors)]
    communities = nx.algorithms.community.greedy_modularity_communities(graph, weight="weight")
    output: list[dict[str, Any]] = []
    for community_id, members in enumerate(communities, start=1):
        for actor in sorted(members):
            output.append(
                {
                    "actor_id": actor,
                    "community": community_id,
                    "method": "greedy_modularity_congruence",
                }
            )
    return output


def fragmentation_summary(statements: Iterable[DiscourseStatement]) -> dict[str, float | int | str]:
    """Describe congruence/conflict structure without claiming substantive polarization."""
    rows = list(statements)
    congruence = actor_projection(rows)
    conflict = actor_projection(rows, conflict=True)
    congruence_weight = sum(float(value["weight"]) for value in congruence.values())
    conflict_weight = sum(float(value["weight"]) for value in conflict.values())
    total_weight = congruence_weight + conflict_weight
    return {
        "congruence_edges": len(congruence),
        "conflict_edges": len(conflict),
        "congruence_weight": congruence_weight,
        "conflict_weight": conflict_weight,
        "conflict_share": conflict_weight / total_weight if total_weight else 0.0,
        "interpretation": "descriptive conflict share; not a validated measure of political polarization",
    }


def coverage_summary(statements: Iterable[DiscourseStatement]) -> dict[str, int]:
    rows = list(statements)
    return {
        "statements": len(rows),
        "actors": len({s.actor_id for s in rows}),
        "concepts": len({s.concept_id for s in rows}),
        "unknown_stance": sum(s.stance == Stance.UNKNOWN for s in rows),
        "abstained": sum(s.abstained for s in rows),
        "validated": sum(s.validation_status.value == "validated" for s in rows),
        "exact_evidence": sum(s.evidence.exact for s in rows),
    }
