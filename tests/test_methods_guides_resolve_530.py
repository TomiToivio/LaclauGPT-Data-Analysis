"""The methods guides must describe the tree they live in (#530).

Three guides now explain the Phase 1 paper to researchers — `docs/AI26_PHASE1_METHOD.md`,
`docs/methods/RESEARCH_METHOD_GUIDE.md` and `docs/methods/phase1_researcher_guide.md` — written in parallel
for the same issue. Whichever one a reader lands on, it must not send them to a module that was renamed or
an analysis field that no longer exists.

These tests check only that the names resolve: every repository path a guide links, every module it names in
backticks, and every `analysis.*` / `source.*` field it cites. They deliberately do not compare the guides to
each other or judge their prose — that argument belongs to the paper.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from laclaugpt_data_analysis.canonical import AnalysisSection, CanonicalRecord

ROOT = Path(__file__).resolve().parents[1]
GUIDES = [
    ROOT / "docs" / "AI26_PHASE1_METHOD.md",
    ROOT / "docs" / "methods" / "RESEARCH_METHOD_GUIDE.md",
    ROOT / "docs" / "methods" / "phase1_researcher_guide.md",
]
PAPER_URL = "https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md"


def existing_guides() -> list[Path]:
    return [guide for guide in GUIDES if guide.is_file()]


def test_at_least_one_guide_exists():
    assert existing_guides(), "the researcher-facing method guide has been removed; restore it or update this test"


@pytest.mark.parametrize("guide", existing_guides(), ids=lambda p: p.name)
def test_it_cites_the_paper_as_authority(guide: Path):
    assert PAPER_URL in guide.read_text(encoding="utf-8"), f"{guide.name} must name the Phase 1 paper"


@pytest.mark.parametrize("guide", existing_guides(), ids=lambda p: p.name)
def test_every_linked_path_resolves(guide: Path):
    text = guide.read_text(encoding="utf-8")
    linked = set(re.findall(r"\]\((\.{0,2}/?[A-Za-z0-9_./-]+\.(?:py|md))(?:#[^)]*)?\)", text))
    unresolved = sorted(link for link in linked
                        if not (guide.parent / link).resolve().exists()
                        and not (ROOT / link).resolve().exists())
    assert not unresolved, f"{guide.name} links paths that do not exist: {unresolved}"


@pytest.mark.parametrize("guide", existing_guides(), ids=lambda p: p.name)
def test_every_module_named_in_backticks_exists(guide: Path, request):
    """A guide may name a module as `summary.py` instead of linking it; the name must still resolve.

    Resolution is by filename anywhere under `src/`, which is how a researcher would search for it, plus the
    repository root for top-level scripts.
    """
    text = guide.read_text(encoding="utf-8")
    named = {name for name in re.findall(r"`([A-Za-z0-9_/]+\.py)`", text) if "/" not in name}
    known = {path.name for path in (ROOT / "src").rglob("*.py")}
    known |= {path.name for path in ROOT.glob("*.py")}
    missing = sorted(name for name in named if name not in known)
    assert not missing, f"{guide.name} names modules that do not exist anywhere under src/: {missing}"


@pytest.mark.parametrize("guide", existing_guides(), ids=lambda p: p.name)
def test_every_analysis_field_it_mentions_exists(guide: Path):
    fields = set(AnalysisSection.model_fields)
    mentioned = set(re.findall(r"analysis\.([a-z_]+)(?![a-z0-9_])", guide.read_text(encoding="utf-8")))
    missing = sorted(mentioned - fields)
    assert not missing, (
        f"{guide.name} cites analysis fields that AnalysisSection does not declare: {missing}. "
        "A renamed or retired field must be corrected in the guide, not left for a reader to discover."
    )


@pytest.mark.parametrize("guide", existing_guides(), ids=lambda p: p.name)
def test_every_source_field_it_mentions_exists(guide: Path):
    annotation = CanonicalRecord.model_fields["source"].annotation
    source_fields = set(annotation.model_fields) if hasattr(annotation, "model_fields") else set()
    mentioned = set(re.findall(r"source\.([a-z_]+)(?![a-z0-9_])", guide.read_text(encoding="utf-8")))
    missing = sorted(mentioned - source_fields)
    assert not missing, f"{guide.name} cites source fields that do not exist: {missing}"


@pytest.mark.parametrize("guide", existing_guides(), ids=lambda p: p.name)
def test_it_does_not_claim_a_completed_validation(guide: Path):
    """The paper's validation is proposed; a guide that implies it happened would be a false claim."""
    lowered = guide.read_text(encoding="utf-8").lower()
    assert any(phrase in lowered for phrase in (
        "not demonstrated", "should not be reported", "not be reported as", "proposed",
        "no completed", "not evidence of interpretive", "not evidence that",
    )), f"{guide.name} must distinguish proposed validation from completed evaluation"
