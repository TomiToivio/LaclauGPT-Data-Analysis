"""Experimental Bourdieu-inspired social-space analysis.

This module deliberately keeps field position, discourse position, and ideology
separate.  It implements a small, dependency-light MCA/GDA core suitable for
AI26 experiments and visualization exports.  Interpretive labels remain a
human/researcher responsibility.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from . import BackendUnavailable


@dataclass(frozen=True)
class SocialSpaceConfig:
    """Configuration and provenance for one social-space fit."""

    unit: str = "actor"
    active_variables: tuple[str, ...] = ()
    supplementary_variables: tuple[str, ...] = ()
    id_field: str = "id"
    missing_label: str = "__MISSING__"
    n_components: int = 2
    method: str = "mca"
    codebook_version: str = ""
    sampling_frame: str = ""
    weighting: str = "uniform"
    discretization: Mapping[str, str] = field(default_factory=dict)


@dataclass
class SocialSpaceResult:
    """Visualization-friendly MCA result with explicit provenance."""

    method: str
    unit: str
    dimensions: list[str]
    eigenvalues: list[float]
    inertia_ratio: list[float]
    row_coordinates: list[dict[str, Any]]
    category_coordinates: list[dict[str, Any]]
    category_contributions: list[dict[str, Any]]
    row_cos2: list[dict[str, Any]]
    category_cos2: list[dict[str, Any]]
    supplementary_coordinates: list[dict[str, Any]]
    frequencies: list[dict[str, Any]]
    provenance: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def visualization_payload(self) -> dict[str, Any]:
        """Return stable tables intended for Data-Visualization ingestion."""
        return {
            "schema": "laclaugpt.social-space.v1",
            "method": self.method,
            "unit": self.unit,
            "dimensions": self.dimensions,
            "eigenvalues": self.eigenvalues,
            "inertia_ratio": self.inertia_ratio,
            "points": self.row_coordinates,
            "categories": self.category_coordinates,
            "category_contributions": self.category_contributions,
            "row_cos2": self.row_cos2,
            "category_cos2": self.category_cos2,
            "supplementary": self.supplementary_coordinates,
            "frequencies": self.frequencies,
            "provenance": self.provenance,
        }


def _numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise BackendUnavailable(
            "Social-space MCA requires the optional analysis dependencies; "
            "install laclaugpt-data-analysis[analysis]."
        ) from exc
    return np


def _value(record: Mapping[str, Any], variable: str, missing_label: str) -> str:
    value = record.get(variable)
    if value is None or value == "":
        return missing_label
    return str(value)


def _validate(records: Sequence[Mapping[str, Any]], config: SocialSpaceConfig) -> None:
    if not records:
        raise ValueError("MCA requires at least one row")
    if len(config.active_variables) < 2:
        raise ValueError("MCA requires at least two active categorical variables")
    if config.n_components < 1:
        raise ValueError("n_components must be >= 1")
    if config.method != "mca":
        raise ValueError("Only method='mca' is implemented by this prototype")
    ids = [str(row.get(config.id_field, "")) for row in records]
    if any(not value for value in ids):
        raise ValueError(f"Every row must retain canonical identifier field {config.id_field!r}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"Identifier field {config.id_field!r} must be unique")


def fit_mca(
    records: Sequence[Mapping[str, Any]],
    config: SocialSpaceConfig,
) -> SocialSpaceResult:
    """Fit MCA to categorical actor/document rows using complete disjunctive coding.

    This is correspondence analysis of the complete disjunctive table.  The
    implementation intentionally exposes masses, contributions and cos²-derived
    quality measures rather than auto-naming axes or ideological clusters.
    """
    _validate(records, config)
    np = _numpy()

    categories: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for variable in config.active_variables:
        for row in records:
            category = (variable, _value(row, variable, config.missing_label))
            if category not in seen:
                seen.add(category)
                categories.append(category)

    n_rows = len(records)
    n_vars = len(config.active_variables)
    indicator = np.zeros((n_rows, len(categories)), dtype=float)
    category_index = {category: idx for idx, category in enumerate(categories)}
    for row_idx, row in enumerate(records):
        for variable in config.active_variables:
            key = (variable, _value(row, variable, config.missing_label))
            indicator[row_idx, category_index[key]] = 1.0

    grand_total = float(indicator.sum())
    p = indicator / grand_total
    row_masses = p.sum(axis=1)
    col_masses = p.sum(axis=0)
    if np.any(col_masses <= 0):  # defensive; impossible after category construction
        raise ValueError("MCA encountered an empty active category")

    expected = np.outer(row_masses, col_masses)
    standardized = (p - expected) / np.sqrt(np.outer(row_masses, col_masses))
    u, singular_values, vt = np.linalg.svd(standardized, full_matrices=False)
    eigenvalues_all = singular_values**2

    max_rank = min(n_rows - 1, len(categories) - n_vars)
    n_components = min(config.n_components, max(1, max_rank), len(singular_values))
    singular_values = singular_values[:n_components]
    eigenvalues = eigenvalues_all[:n_components]
    u = u[:, :n_components]
    v = vt.T[:, :n_components]

    row_coordinates = (u * singular_values) / np.sqrt(row_masses[:, None])
    category_coordinates = (v * singular_values) / np.sqrt(col_masses[:, None])

    total_inertia = float(eigenvalues_all.sum())
    inertia_ratio = [float(value / total_inertia) if total_inertia else 0.0 for value in eigenvalues]
    dimensions = [f"Dim{i + 1}" for i in range(n_components)]

    row_distance2 = np.sum(row_coordinates**2, axis=1)
    category_distance2 = np.sum(category_coordinates**2, axis=1)

    row_rows: list[dict[str, Any]] = []
    row_cos2_rows: list[dict[str, Any]] = []
    for idx, record in enumerate(records):
        point = {"id": str(record[config.id_field])}
        quality = {"id": str(record[config.id_field])}
        for dim_idx, dim in enumerate(dimensions):
            point[dim] = float(row_coordinates[idx, dim_idx])
            denom = float(row_distance2[idx])
            quality[dim] = float(row_coordinates[idx, dim_idx] ** 2 / denom) if denom else 0.0
        row_rows.append(point)
        row_cos2_rows.append(quality)

    category_rows: list[dict[str, Any]] = []
    contribution_rows: list[dict[str, Any]] = []
    category_cos2_rows: list[dict[str, Any]] = []
    frequency_rows: list[dict[str, Any]] = []
    for idx, (variable, category) in enumerate(categories):
        point: dict[str, Any] = {"variable": variable, "category": category}
        contribution: dict[str, Any] = {"variable": variable, "category": category}
        quality: dict[str, Any] = {"variable": variable, "category": category}
        for dim_idx, dim in enumerate(dimensions):
            coord = float(category_coordinates[idx, dim_idx])
            point[dim] = coord
            eig = float(eigenvalues[dim_idx])
            contribution[dim] = (
                float(col_masses[idx] * category_coordinates[idx, dim_idx] ** 2 / eig)
                if eig
                else 0.0
            )
            denom = float(category_distance2[idx])
            quality[dim] = float(coord**2 / denom) if denom else 0.0
        category_rows.append(point)
        contribution_rows.append(contribution)
        category_cos2_rows.append(quality)
        frequency_rows.append(
            {
                "variable": variable,
                "category": category,
                "count": int(indicator[:, idx].sum()),
                "proportion": float(indicator[:, idx].mean()),
            }
        )

    supplementary_rows: list[dict[str, Any]] = []
    for variable in config.supplementary_variables:
        values = sorted({_value(row, variable, config.missing_label) for row in records})
        for category in values:
            member_indices = [
                idx
                for idx, row in enumerate(records)
                if _value(row, variable, config.missing_label) == category
            ]
            point: dict[str, Any] = {
                "variable": variable,
                "category": category,
                "n": len(member_indices),
            }
            if member_indices:
                barycenter = row_coordinates[member_indices].mean(axis=0)
                for dim_idx, dim in enumerate(dimensions):
                    point[dim] = float(barycenter[dim_idx])
            supplementary_rows.append(point)

    provenance = {
        "schema": "laclaugpt.social-space.v1",
        "unit": config.unit,
        "method": config.method,
        "id_field": config.id_field,
        "active_variables": list(config.active_variables),
        "supplementary_variables": list(config.supplementary_variables),
        "missing_data": {"strategy": "explicit-category", "label": config.missing_label},
        "discretization": dict(config.discretization),
        "weighting": config.weighting,
        "sampling_frame": config.sampling_frame,
        "codebook_version": config.codebook_version,
        "n_rows": n_rows,
        "n_active_variables": n_vars,
        "n_active_categories": len(categories),
        "dimension_naming": "researcher-required",
        "interpretation_warning": (
            "Geometric proximity is descriptive, not causal and not a literal social tie. "
            "Computational axes/clusters are not automatically fields, classes, ideologies, or hegemonic blocs."
        ),
    }

    return SocialSpaceResult(
        method="mca",
        unit=config.unit,
        dimensions=dimensions,
        eigenvalues=[float(value) for value in eigenvalues],
        inertia_ratio=inertia_ratio,
        row_coordinates=row_rows,
        category_coordinates=category_rows,
        category_contributions=contribution_rows,
        row_cos2=row_cos2_rows,
        category_cos2=category_cos2_rows,
        supplementary_coordinates=supplementary_rows,
        frequencies=frequency_rows,
        provenance=provenance,
    )


def hierarchical_clusters(
    result: SocialSpaceResult,
    *,
    n_clusters: int = 3,
) -> list[dict[str, Any]]:
    """Optional HCPC-style exploratory clustering on retained MCA coordinates.

    Cluster IDs are deliberately neutral numeric labels.  This helper must not be
    used to name classes, ideologies, fields, or discourse coalitions automatically.
    """
    if n_clusters < 1:
        raise ValueError("n_clusters must be >= 1")
    try:
        import numpy as np
        from scipy.cluster.hierarchy import fcluster, linkage
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise BackendUnavailable(
            "Hierarchical social-space clustering requires laclaugpt-data-analysis[analysis]."
        ) from exc

    if len(result.row_coordinates) < 2:
        return [{"id": row["id"], "cluster": 1} for row in result.row_coordinates]
    coordinates = np.asarray(
        [[row[dim] for dim in result.dimensions] for row in result.row_coordinates],
        dtype=float,
    )
    tree = linkage(coordinates, method="ward")
    labels = fcluster(tree, t=min(n_clusters, len(coordinates)), criterion="maxclust")
    return [
        {"id": row["id"], "cluster": int(label)}
        for row, label in zip(result.row_coordinates, labels, strict=True)
    ]


def category_enrichment(
    records: Sequence[Mapping[str, Any]],
    clusters: Sequence[Mapping[str, Any]],
    *,
    id_field: str,
    variable: str,
    missing_label: str = "__MISSING__",
) -> list[dict[str, Any]]:
    """Describe category proportions by cluster without assigning semantic labels."""
    cluster_by_id = {str(row["id"]): int(row["cluster"]) for row in clusters}
    counts: dict[tuple[int, str], int] = {}
    totals: dict[int, int] = {}
    for record in records:
        record_id = str(record[id_field])
        if record_id not in cluster_by_id:
            continue
        cluster = cluster_by_id[record_id]
        category = _value(record, variable, missing_label)
        counts[(cluster, category)] = counts.get((cluster, category), 0) + 1
        totals[cluster] = totals.get(cluster, 0) + 1
    return [
        {
            "cluster": cluster,
            "variable": variable,
            "category": category,
            "count": count,
            "proportion": count / totals[cluster],
        }
        for (cluster, category), count in sorted(counts.items())
    ]
