from datetime import datetime, timezone

from laclaugpt_data_analysis.discourse_network import (
    DiscourseStatement,
    EvidenceSpan,
    actor_concept_matrix,
    actor_projection,
    concept_projection,
    dna_actor_projection,
    dna_binary_actor_concept,
    dna_concept_projection,
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


def test_dna_binary_projection_matches_stacked_support_rejection_semantics():
    rows = [
        _s("1", "a", "x", "support"),
        _s("2", "a", "x", "support"),
        _s("3", "b", "x", "support"),
        _s("4", "c", "x", "oppose"),
        _s("5", "a", "y", "oppose"),
        _s("6", "b", "y", "oppose"),
        _s("7", "c", "y", "oppose"),
    ]
    matrix = dna_binary_actor_concept(rows)
    assert matrix["a"]["x"][True] == 2
    assert dna_actor_projection(rows)[("a", "b")]["weight"] == 3.0
    assert dna_actor_projection(rows, conflict=True)[("a", "c")]["weight"] == 2.0
    assert dna_concept_projection(rows)[("x", "y")]["weight"] == 1.0
    assert dna_concept_projection(rows, conflict=True)[("x", "y")]["weight"] == 3.0


def test_dna_projection_excludes_uncoded_stances():
    rows = [
        _s("1", "a", "x", "neutral"),
        _s("2", "b", "x", "support"),
        _s("3", "c", "x", "unknown"),
    ]
    matrix = dna_binary_actor_concept(rows)
    assert "a" not in matrix
    assert "c" not in matrix
    assert "b" in matrix
