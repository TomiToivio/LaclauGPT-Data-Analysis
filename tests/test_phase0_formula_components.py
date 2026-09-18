from laclaugpt_discourse import (
    AffectObservation,
    FormulaComponents,
    FrontierConstruct,
    UsConstruct,
    to_graph_observations,
)


def test_components_are_independent():
    result = FormulaComponents(
        us_constructs=[
            UsConstruct(
                label="workers",
                text_span="we workers",
                confidence=0.9,
                source_date="2026-09-18",
            )
        ],
        frontier_constructs=[],
        affects=[
            AffectObservation(
                affect="hope",
                target="public AI",
                text_span="we hope public AI will benefit everyone",
                confidence=0.8,
                source_date="2026-09-18",
            )
        ],
    )

    assert len(result.us_constructs) == 1
    assert result.frontier_constructs == []
    assert len(result.affects) == 1
    assert not hasattr(result, "is_populist")
    assert not hasattr(result, "populism_score")


def test_frontier_can_exist_without_us():
    result = FormulaComponents(
        frontier_constructs=[
            FrontierConstruct(
                us_side=None,
                them_side="Big Tech",
                relation="blame",
                text_span="Big Tech is responsible for the harm",
                confidence=0.76,
                source_date="2026-09-18",
            )
        ]
    )
    assert result.frontier_constructs[0].us_side is None


def test_graph_projection_preserves_time_evidence_and_provenance():
    result = FormulaComponents(
        us_constructs=[
            UsConstruct(
                label="ordinary people",
                text_span="ordinary people like us",
                confidence=0.91,
                source_date="2026-09-18",
            )
        ],
        frontier_constructs=[
            FrontierConstruct(
                us_side="ordinary people",
                them_side="AI corporations",
                relation="antagonistic_boundary",
                text_span="corporations are taking control away from ordinary people",
                confidence=0.87,
                source_date="2026-09-18",
            )
        ],
        affects=[
            AffectObservation(
                affect="fear",
                target="AI corporations",
                text_span="people are afraid of losing control",
                confidence=0.82,
                source_date="2026-09-18",
            )
        ],
    )

    observations = to_graph_observations(
        result,
        source_url="https://example.org/article",
        document_id="doc-1",
    )

    assert {row["kind"] for row in observations} == {
        "us_construct",
        "frontier_construct",
        "affect",
    }
    assert all(row["source_date"] == "2026-09-18" for row in observations)
    assert all(row["source_url"] == "https://example.org/article" for row in observations)
    assert all(row["text_span"] for row in observations)
