from __future__ import annotations

import pytest

from laclaugpt_data_analysis.analysis.social_space import (
    SocialSpaceConfig,
    category_enrichment,
    fit_mca,
    hierarchical_clusters,
)

pytest.importorskip("numpy")


@pytest.fixture
def actor_rows() -> list[dict[str, object]]:
    return [
        {
            "actor_id": "a1",
            "arena": "elite",
            "institution": "lab",
            "frame": "acceleration",
            "imaginary": "abundance",
            "country": "US",
        },
        {
            "actor_id": "a2",
            "arena": "elite",
            "institution": "safety-org",
            "frame": "catastrophic-risk",
            "imaginary": "x-risk",
            "country": "US",
        },
        {
            "actor_id": "a3",
            "arena": "grassroots",
            "institution": "civil-society",
            "frame": "structural-harm",
            "imaginary": "critical-ai",
            "country": "FI",
        },
        {
            "actor_id": "a4",
            "arena": "parliamentary",
            "institution": "party",
            "frame": "regulation",
            "imaginary": "governance",
            "country": "FI",
        },
        {
            "actor_id": "a5",
            "arena": "grassroots",
            "institution": "civil-society",
            "frame": "structural-harm",
            "imaginary": "critical-ai",
            "country": "KE",
        },
        {
            "actor_id": "a6",
            "arena": "elite",
            "institution": "lab",
            "frame": "acceleration",
            "imaginary": "abundance",
            "country": "US",
        },
    ]


def test_fit_mca_preserves_ids_and_provenance(actor_rows: list[dict[str, object]]) -> None:
    result = fit_mca(
        actor_rows,
        SocialSpaceConfig(
            unit="actor",
            id_field="actor_id",
            active_variables=("arena", "institution", "frame"),
            supplementary_variables=("imaginary", "country"),
            n_components=2,
            codebook_version="ai26-test-v1",
            sampling_frame="synthetic-test",
        ),
    )

    assert result.method == "mca"
    assert result.dimensions == ["Dim1", "Dim2"]
    assert {row["id"] for row in result.row_coordinates} == {
        "a1",
        "a2",
        "a3",
        "a4",
        "a5",
        "a6",
    }
    assert result.provenance["active_variables"] == ["arena", "institution", "frame"]
    assert result.provenance["codebook_version"] == "ai26-test-v1"
    assert result.provenance["dimension_naming"] == "researcher-required"
    assert result.category_contributions
    assert result.category_cos2
    assert result.supplementary_coordinates
    assert abs(sum(result.inertia_ratio)) <= 1.0 + 1e-9


def test_visualization_payload_has_stable_schema(actor_rows: list[dict[str, object]]) -> None:
    result = fit_mca(
        actor_rows,
        SocialSpaceConfig(
            id_field="actor_id",
            active_variables=("arena", "institution"),
            supplementary_variables=("imaginary",),
        ),
    )
    payload = result.visualization_payload()

    assert payload["schema"] == "laclaugpt.social-space.v1"
    assert payload["points"] == result.row_coordinates
    assert payload["categories"] == result.category_coordinates
    assert payload["provenance"]["interpretation_warning"]


def test_missing_values_are_explicit_categories() -> None:
    rows = [
        {"id": "1", "arena": "elite", "frame": "risk"},
        {"id": "2", "arena": "grassroots", "frame": None},
        {"id": "3", "arena": "elite", "frame": "growth"},
    ]
    result = fit_mca(
        rows,
        SocialSpaceConfig(active_variables=("arena", "frame"), n_components=1),
    )

    assert any(
        row["variable"] == "frame" and row["category"] == "__MISSING__"
        for row in result.frequencies
    )


def test_requires_unique_canonical_ids(actor_rows: list[dict[str, object]]) -> None:
    rows = list(actor_rows)
    rows[1] = {**rows[1], "actor_id": "a1"}
    with pytest.raises(ValueError, match="must be unique"):
        fit_mca(
            rows,
            SocialSpaceConfig(
                id_field="actor_id",
                active_variables=("arena", "institution"),
            ),
        )


def test_optional_hierarchical_clustering_and_enrichment(
    actor_rows: list[dict[str, object]],
) -> None:
    pytest.importorskip("scipy")
    result = fit_mca(
        actor_rows,
        SocialSpaceConfig(
            id_field="actor_id",
            active_variables=("arena", "institution", "frame"),
        ),
    )
    clusters = hierarchical_clusters(result, n_clusters=2)
    enrichment = category_enrichment(
        actor_rows,
        clusters,
        id_field="actor_id",
        variable="imaginary",
    )

    assert len(clusters) == len(actor_rows)
    assert {row["cluster"] for row in clusters} <= {1, 2}
    assert enrichment
    assert all("proportion" in row for row in enrichment)
