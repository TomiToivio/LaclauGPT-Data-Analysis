from datetime import UTC, datetime

from laclaugpt_data_analysis.analysis.social_space import SocialSpaceConfig
from laclaugpt_data_analysis.discourse_network import DiscourseStatement, EvidenceSpan
from laclaugpt_data_analysis.framing import FrameElement, FrameKind, FrameProposal
from laclaugpt_data_analysis.multimethod import build_ai26_artifact


def _statement(
    statement_id: str,
    actor: str,
    concept: str,
    stance: str,
    day: int,
    *,
    arena: str = "elite",
) -> DiscourseStatement:
    quote = f"{actor} statement about {concept}"
    return DiscourseStatement(
        statement_id=statement_id,
        source_url=f"https://example.org/{statement_id}",
        source_record_id=f"record-{statement_id}",
        actor_id=actor,
        actor_name=actor,
        concept_id=concept,
        concept_label=concept,
        proposition=quote,
        stance=stance,
        timestamp=datetime(2026, 9, day, tzinfo=UTC),
        evidence=EvidenceSpan(quote=quote, start_char=0, end_char=len(quote), exact=True),
        project_id="ai26",
        arena=arena,
        platform="rss",
        confidence=0.9,
        coder_type="model",
        coder_id_or_model="fixture-model",
        model_provider="test",
        model_version="1",
        codebook_version="ai26-test-v1",
    )


def test_ai26_bundle_integrates_claims_frames_dna_and_mca():
    statements = [
        _statement("s1", "actor-a", "rapid-development", "support", 1),
        _statement("s2", "actor-b", "rapid-development", "support", 2),
        _statement("s3", "actor-c", "rapid-development", "oppose", 3),
        _statement("s4", "actor-c", "worker-protection", "support", 10, arena="grassroots"),
    ]
    frame = FrameProposal(
        frame_id="f1",
        statement_id="s3",
        source_record_id="record-s3",
        source_url="https://example.org/s3",
        project_id="ai26",
        arena="elite",
        platform="rss",
        elements=[
            FrameElement(
                kind=FrameKind.PROBLEM,
                text="Rapid development creates social risk",
                evidence=EvidenceSpan(
                    quote="actor-c statement about rapid-development",
                    start_char=0,
                    end_char=len("actor-c statement about rapid-development"),
                    exact=True,
                ),
                confidence=0.9,
            )
        ],
    )
    social_rows = [
        {"id": "actor-a", "actor_type": "founder", "arena": "elite", "formation": "accelerationist"},
        {"id": "actor-b", "actor_type": "researcher", "arena": "elite", "formation": "techno-optimist"},
        {"id": "actor-c", "actor_type": "researcher", "arena": "grassroots", "formation": "critical-ai"},
    ]
    config = SocialSpaceConfig(
        unit="actor",
        id_field="id",
        active_variables=("actor_type", "arena"),
        supplementary_variables=("formation",),
        codebook_version="ai26-test-v1",
        sampling_frame="synthetic public fixture",
    )

    artifact = build_ai26_artifact(
        statements,
        frames=[frame],
        social_space_records=social_rows,
        social_space_config=config,
        cluster_count=2,
        temporal_window_days=7,
        analysis_run_id="fixture-run",
    )

    assert artifact["schema"] == "laclaugpt.multimethod.v1"
    assert len(artifact["statements"]) == 4
    assert artifact["frames"][0]["statement_id"] == "s3"
    assert artifact["dna"]["actor_congruence"]
    assert artifact["dna"]["actor_conflict"]
    assert len(artifact["dna"]["temporal_windows"]) == 2
    assert artifact["mca"]["schema"] == "laclaugpt.social-space.v1"
    assert artifact["mca_clusters"]
    supplementary = artifact["mca"]["supplementary"]
    assert any(row["variable"] == "formation" for row in supplementary)


def test_ai26_filters_and_abstention_do_not_create_false_network_positions():
    statements = [
        _statement("s1", "actor-a", "x", "support", 1),
        _statement("s2", "actor-b", "x", "support", 1),
        DiscourseStatement(
            statement_id="s3",
            source_url="https://example.org/s3",
            actor_id="actor-c",
            actor_name="actor-c",
            concept_id="x",
            concept_label="x",
            stance="unknown",
            project_id="ai26",
            arena="elite",
            platform="rss",
            abstained=True,
        ),
        DiscourseStatement(
            statement_id="other",
            source_url="https://example.org/other",
            actor_id="actor-z",
            actor_name="actor-z",
            concept_id="x",
            concept_label="x",
            stance="oppose",
            project_id="other-project",
            arena="elite",
            platform="rss",
            evidence=EvidenceSpan(quote="other evidence"),
        ),
    ]
    artifact = build_ai26_artifact(statements, arena="elite", platform="rss")
    assert {row["statement_id"] for row in artifact["statements"]} == {"s1", "s2", "s3"}
    assert artifact["dna"]["coverage"]["abstained"] == 1
    assert all(edge["source"] != "actor-c" and edge["target"] != "actor-c" for edge in artifact["dna"]["actor_congruence"])
