"""The methods guide must describe the tree it lives in (#530).

A researcher-facing guide is worse than none when it cites a field that no longer exists or a test file
that was renamed: the reader concludes the code is broken, or that the guide is. These tests hold the guide
to the current schema and the current tree, so it fails here instead of misleading someone.

They are deliberately narrow. They check that *names exist*, not that the prose is good — the argument in
the guide is a claim about the paper, and no test can adjudicate it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from laclaugpt_data_analysis.canonical import AnalysisSection, CanonicalRecord

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "methods" / "phase1_researcher_guide.md"
PAPER_URL = "https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md"


@pytest.fixture(scope="module")
def guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def test_the_guide_exists_and_is_linked_from_the_documentation_entry_point():
    assert GUIDE.is_file()
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "methods/phase1_researcher_guide.md" in index, (
        "a researcher who starts from docs/README.md must be able to reach the methods guide"
    )


def test_it_names_the_paper_it_is_authoritative_from(guide):
    assert PAPER_URL in guide
    for section in ("§2", "§3.1", "§3.4", "§4"):
        assert section in guide, section


def test_every_analysis_field_it_mentions_exists(guide):
    fields = set(AnalysisSection.model_fields)
    mentioned = set(re.findall(r"analysis\.([a-z_]+)", guide))
    missing = sorted(mentioned - fields)
    assert not missing, (
        f"the guide cites analysis fields that AnalysisSection does not declare: {missing}. "
        "Either the guide is stale or the field was renamed — a reader would look for it and not find it."
    )


def test_every_source_field_it_mentions_exists(guide):
    source_fields = set(CanonicalRecord.model_fields["source"].annotation.model_fields)
    mentioned = set(re.findall(r"source\.([a-z_]+)", guide))
    missing = sorted(mentioned - source_fields)
    assert not missing, f"the guide cites source fields that do not exist: {missing}"


def test_every_path_it_cites_exists(guide):
    paths = set(
        re.findall(r"`((?:src|tests|tools|laclaugpt|docs)/[A-Za-z0-9_./-]+\.(?:py|md))`", guide)
    )
    assert paths, "the guide should point at code, not only describe it"
    missing = sorted(p for p in paths if not (ROOT / p).exists())
    assert not missing, f"the guide cites paths that do not exist: {missing}"


def test_the_retired_and_unproduced_fields_are_reported_as_such(guide):
    """The guide's §7 is a list of mismatches; if a mismatch is fixed the list must change too."""
    from laclaugpt_data_analysis.field_contract import UNPRODUCED_FIELDS

    for field in (
        "embeddings",
        "entity_mentions",
        "representations",
        "us",
        "them",
        "topic_assignments",
    ):
        assert field in UNPRODUCED_FIELDS, f"{field} is no longer registered as unproduced — update §7"
        assert field in guide, f"§7 should report the unproduced field {field}"


def test_it_does_not_claim_an_accuracy_result(guide):
    """The paper's validation is proposed; a guide that implies it was completed would be a false claim."""
    # The guide's own wording for this is "not demonstrated here" / "should be reported as completed
    # validation"; any of those phrasings counts, so the test tracks the claim rather than one sentence.
    lowered = guide.lower()
    assert any(
        phrase in lowered
        for phrase in (
            "not demonstrated",
            "not be reported as **completed validation**",
            "completed, independently adjudicated evaluation is **not",
        )
    ), "the guide must say the evaluation is not done, not imply it is"
    for forbidden in ("we measured an accuracy of", "inter-coder agreement of", "koppas alpha"):
        assert forbidden not in lowered


def test_the_worked_example_uses_real_field_names(guide):
    for field in (
        "review_status",
        "evidence_ids",
        "start_offset",
        "end_offset",
        "formula_of_populism",
        "empty_signifier_candidates",
        "uncertainty",
    ):
        assert field in guide, field
