from datetime import datetime, timezone

from laclaugpt_data_analysis.discourse_network import (
    DiscourseStatement,
    EvidenceSpan,
    actor_concept_matrix,
    actor_projection,
    concept_projection,
    fixed_windows,
)


def _s(statement_id: str, actor: str, concept: str, stance: str, day: int = 1):
    return DiscourseStatement(
        statement_id=statement_id,
        source_url=f"https://example.org/{statement_id}",
        actor_id=actor,
        actor_name=actor,
        concept_id=concept,
        concept_label=concept,
        stance=stance,
        timestamp=datetime(2026, 1, day, tzinfo=timezone.utc),
        evidence=EvidenceSpan(quote="evidence", start_char=0, end_char=8, exact=True),
    )


def test_actor_congruence_and_conflict():
    rows = [
        _s("1", "a", "x", "support"),
        _s("2", "b", "x", "support"),
        _s("3", "c", "x", "oppose"),
    ]
    matrix = actor_concept_matrix(rows)
    assert matrix["a"]["x"] == 1
    assert ("a", "b") in actor_projection(rows)
    assert ("a", "c") in actor_projection(rows, conflict=True)


def test_concept_projection_and_windows():
    rows = [
        _s("1", "a", "x", "support", 1),
        _s("2", "a", "y", "support", 1),
        _s("3", "b", "x", "support", 9),
        _s("4", "b", "y", "oppose", 9),
    ]
    assert ("x", "y") in concept_projection(rows)
    assert ("x", "y") in concept_projection(rows, conflict=True)
    windows = fixed_windows(rows, days=7)
    assert len(windows) == 2
