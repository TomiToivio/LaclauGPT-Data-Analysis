"""Integrated AI26 multi-method analysis contract.

The module joins evidence-linked claims, framing, DNA projections and optional MCA
without promoting any one method to theoretical ground truth.  It is storage-neutral:
callers can source rows from CSV/SQLite/MongoDB and persist the returned JSON-ready
artifact through the repository's existing storage adapters.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .analysis.social_space import SocialSpaceConfig, fit_mca, hierarchical_clusters
from .discourse_network import (
    DiscourseStatement,
    actor_projection,
    community_assignments,
    concept_projection,
    coverage_summary,
    fixed_windows,
    fragmentation_summary,
)
from .framing import FrameProposal, frame_frequency, frame_table

SCHEMA_VERSION = "laclaugpt.multimethod.v1"


def _edges(edges: Mapping[tuple[str, str], Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"source": left, "target": right, **dict(data)}
        for (left, right), data in sorted(edges.items())
    ]


def statement_table(statements: Sequence[DiscourseStatement]) -> list[dict[str, Any]]:
    """Export shared claim rows while retaining source/evidence/provenance links."""
    return [statement.model_dump(mode="json") for statement in statements]


def filter_statements(
    statements: Sequence[DiscourseStatement],
    *,
    project_id: str | None = None,
    arena: str | None = None,
    platform: str | None = None,
) -> list[DiscourseStatement]:
    """Apply explicit metadata filters without inferring missing metadata."""
    rows = list(statements)
    if project_id is not None:
        rows = [row for row in rows if row.project_id == project_id]
    if arena is not None:
        rows = [row for row in rows if row.arena == arena]
    if platform is not None:
        rows = [row for row in rows if row.platform == platform]
    return rows


def _temporal_networks(statements: Sequence[DiscourseStatement], days: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for start, end, rows in fixed_windows(statements, days=days):
        output.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "coverage": coverage_summary(rows),
                "actor_congruence": _edges(actor_projection(rows)),
                "actor_conflict": _edges(actor_projection(rows, conflict=True)),
                "fragmentation": fragmentation_summary(rows),
            }
        )
    return output


def build_multimethod_artifact(
    statements: Sequence[DiscourseStatement],
    *,
    frames: Sequence[FrameProposal] = (),
    social_space_records: Sequence[Mapping[str, Any]] = (),
    social_space_config: SocialSpaceConfig | None = None,
    project_id: str | None = None,
    arena: str | None = None,
    platform: str | None = None,
    temporal_window_days: int = 7,
    cluster_count: int | None = None,
    analysis_run_id: str = "",
    method_version: str = "1",
) -> dict[str, Any]:
    """Build one stable visualization/research artifact from several method projections.

    `social_space_records` are intentionally supplied explicitly rather than generated
    from arbitrary model labels.  Researchers decide which reviewed categorical
    variables are valid active/supplementary modalities before calling MCA.
    """
    selected = filter_statements(
        statements,
        project_id=project_id,
        arena=arena,
        platform=platform,
    )
    statement_ids = {row.statement_id for row in selected}
    selected_frames = [frame for frame in frames if frame.statement_id in statement_ids]

    dna = {
        "coverage": coverage_summary(selected),
        "actor_congruence": _edges(actor_projection(selected)),
        "actor_conflict": _edges(actor_projection(selected, conflict=True)),
        "concept_congruence": _edges(concept_projection(selected)),
        "concept_conflict": _edges(concept_projection(selected, conflict=True)),
        "communities": community_assignments(selected),
        "fragmentation": fragmentation_summary(selected),
        "temporal_windows": _temporal_networks(selected, temporal_window_days),
    }

    mca: dict[str, Any] | None = None
    clusters: list[dict[str, Any]] = []
    if social_space_records and social_space_config is not None:
        result = fit_mca(social_space_records, social_space_config)
        mca = result.visualization_payload()
        if cluster_count is not None:
            clusters = hierarchical_clusters(result, n_clusters=cluster_count)

    return {
        "schema": SCHEMA_VERSION,
        "analysis_run_id": analysis_run_id,
        "method_version": method_version,
        "filters": {
            "project_id": project_id,
            "arena": arena,
            "platform": platform,
            "temporal_window_days": temporal_window_days,
        },
        "statements": statement_table(selected),
        "frames": frame_table(selected_frames),
        "frame_frequency": frame_frequency(selected_frames),
        "dna": dna,
        "mca": mca,
        "mca_clusters": clusters,
        "cross_method": {
            "statement_to_frames": [
                {"statement_id": frame.statement_id, "frame_id": frame.frame_id}
                for frame in selected_frames
            ],
            "actor_to_community": dna["communities"],
            "mca_point_ids": [] if mca is None else [point["id"] for point in mca["points"]],
        },
        "interpretation_guardrail": (
            "Claims, frames, DNA communities/conflict and MCA geometry are descriptive/analytical "
            "objects. They do not automatically establish ideology, equivalence, antagonism, "
            "hegemony, field/class membership, resonance, causality or substantive polarization."
        ),
    }


def build_ai26_artifact(
    statements: Sequence[DiscourseStatement],
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience entry point for the public AI26 reference case."""
    kwargs.setdefault("project_id", "ai26")
    return build_multimethod_artifact(statements, **kwargs)
