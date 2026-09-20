from __future__ import annotations

from laclaugpt_data_analysis.codebooks import CodebookEntry
from laclaugpt_data_analysis.memory.retrieval import context_block, select_relevant_entries


def _entries() -> list[CodebookEntry]:
    return [
        CodebookEntry(
            kind="topic",
            label="data centres",
            aliases=["datacenters"],
            definition="Large computing facilities and their infrastructure.",
            provenance="researcher-codebook",
        ),
        CodebookEntry(
            kind="topic",
            label="labour automation",
            aliases=["job automation"],
            definition="Automation and displacement of paid work.",
            provenance="researcher-codebook",
        ),
        CodebookEntry(
            kind="formation",
            label="AI accelerationism",
            aliases=["e/acc"],
            definition="Researcher-authored sensitising category.",
            provenance="researcher-codebook",
        ),
    ]


def test_selects_only_source_relevant_codebook_concepts() -> None:
    selected, provenance = select_relevant_entries(
        "New datacenters require large amounts of electricity.",
        _entries(),
        limit=8,
        threshold=0.15,
    )

    assert [entry.label for entry in selected] == ["data centres"]
    assert provenance["candidate_count"] == 3
    assert provenance["selected_count"] == 1
    assert provenance["evidence_role"] == "context_not_source_evidence"
    assert provenance["selected"][0]["label"] == "data centres"


def test_disabling_codebook_context_is_independently_reversible() -> None:
    selected, provenance = select_relevant_entries(
        "Datacenters and job automation are both discussed.",
        _entries(),
        enabled=False,
    )

    assert selected == []
    assert provenance["enabled"] is False
    assert provenance["selected_count"] == 0


def test_rendered_context_marks_researcher_codebook_as_non_evidence() -> None:
    block = context_block(
        "The article discusses datacenters.",
        _entries(),
        threshold=0.15,
    )

    assert "Researcher-authored codebook context only" in block
    assert "not source evidence" in block
    assert "data centres" in block
    assert "labour automation" not in block
    assert "AI accelerationism" not in block
