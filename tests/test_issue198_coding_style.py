"""Guard for docs/CODING_STYLE.md (issue #198).

The style guide is a structural promise about the codebase, so it is checked
rather than left as prose that can drift. These are STRUCTURE guards, in the same
spirit as the other issue guards in this repository.

What they protect:

* the guide exists and is reachable from the README and AGENTS.md;
* every principle #198 asked for is actually documented;
* the guide names the **real** conventions of this repository, not an invented
  ones -- the step files, the ``laclaugpt_*.py`` / ``pipeline_*.py``
  infrastructure split, and the theory prompt files;
* the TOMI-LOCKED boundary on the seven scientific steps is not weakened or
  quietly dropped by the guide;
* every file path the guide cites actually exists, so it cannot document a
  module that was renamed or never existed;
* the migration section does not claim a migration that has not happened.

Run: python -m pytest tests/test_issue198_coding_style.py
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUIDE = "docs/CODING_STYLE.md"

#: The principles #198 requires the document to contain.
REQUIRED_TOPICS = (
    "one analysis step = one clearly named file",
    "shared infrastructure",
    "readability over architectural cleverness",
    "logging",
    "comments",
    "system prompts",
    "data flow",
    "self-contained",
)


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def normalised(relative: str) -> str:
    """Whitespace-collapsed, emphasis-stripped text.

    Emphasis marker removal is not cosmetic here: the guide writes key phrases in
    ``**bold**``, and leaving the asterisks in makes a phrase assertion fail on
    correct text.
    """
    text = read(relative)
    text = re.sub(r"[*`]", "", text)
    # Blockquote markers survive whitespace collapsing and split a phrase that is
    # plainly there when rendered, so strip them before matching.
    text = re.sub(r"(?m)^\s*>\s?", " ", text)
    return " ".join(text.split()).lower()


class TestGuideExists:
    def test_guide_exists(self) -> None:
        assert (ROOT / GUIDE).exists(), f"{GUIDE} is missing"

    def test_readme_links_the_guide(self) -> None:
        assert "docs/CODING_STYLE.md" in read("README.md")

    def test_agents_md_links_the_guide(self) -> None:
        assert "docs/CODING_STYLE.md" in read("AGENTS.md")

    def test_guide_states_the_guiding_principle(self) -> None:
        text = normalised(GUIDE)
        assert "optimize for the researcher reading the code six months later" in text

    def test_guide_prioritises_readability_over_abstraction(self) -> None:
        text = normalised(GUIDE)
        assert "readability and research transparency take priority over abstraction" in text


class TestPrincipleCoverage:
    @pytest.mark.parametrize("topic", REQUIRED_TOPICS)
    def test_topic_is_documented(self, topic: str) -> None:
        assert topic in normalised(GUIDE), f"{GUIDE} does not document: {topic}"


class TestRealConventions:
    """The guide must describe this repository, not a generic ideal."""

    def test_names_the_seven_step_files(self) -> None:
        text = normalised(GUIDE)
        for step in (
            "laclaugpt/step_01_preprocess.py",
            "laclaugpt/step_07_sna.py",
        ):
            assert step in text, f"{GUIDE} does not name {step}"

    def test_names_the_infrastructure_module_convention(self) -> None:
        text = normalised(GUIDE)
        assert "laclaugpt_mongo.py" in text
        assert "pipeline_models.py" in text

    def test_names_the_theory_prompt_files(self) -> None:
        text = normalised(GUIDE)
        for prompt in ("prompt_laclau.md", "prompt_dna.md", "prompt_sna.md"):
            assert prompt in text, f"{GUIDE} does not name {prompt}"


class TestLockedBoundary:
    """The guide must not weaken the human-owned step boundary."""

    def test_guide_records_the_steps_are_locked(self) -> None:
        text = normalised(GUIDE)
        assert "tomi-locked" in text

    def test_guide_forbids_restructuring_the_locked_steps(self) -> None:
        text = normalised(GUIDE)
        assert "must not modify, rename, merge, replace or move" in text

    def test_guide_forbids_a_second_step_package(self) -> None:
        text = normalised(GUIDE)
        assert "do not create a parallel step package" in text

    def test_agents_md_still_carries_the_lock(self) -> None:
        """The guide defers to it; it must still exist to defer to."""
        text = normalised("AGENTS.md")
        assert "tomi-locked" in text
        assert "must not modify, rename, merge, replace, regenerate or move" in text


class TestNoOverclaim:
    def test_migration_is_not_claimed_as_done(self) -> None:
        """#198 scopes the migration as future direction; the guide must not overstate."""
        text = normalised(GUIDE)
        assert "status: not started" in text or "**status: not started.**" in text.lower()
        assert "no ep24→ai26 port has been performed" in text

    def test_output_readability_tension_is_addressed_not_ignored(self) -> None:
        """AGENTS.md prioritises machine-readable output; the guide is about code.

        Silently contradicting that rule would be worse than the tension itself, so
        the guide must name it explicitly.
        """
        text = normalised(GUIDE)
        assert "machine-readable canonical records" in text
        assert "nothing here reopens the output question" in text


class TestCitedPathsExist:
    """A guide that cites a renamed or invented file is worse than no guide."""

    #: Backticked relative paths the guide names as real files/directories.
    def test_every_cited_step_and_module_path_exists(self) -> None:
        body = read(GUIDE)
        cited = set(re.findall(r"`((?:laclaugpt|docs|src)/[A-Za-z0-9_./-]+)`", body))
        assert cited, "the guide cites no repository paths; the check would be vacuous"
        missing = sorted(path for path in cited if not (ROOT / path).exists())
        assert not missing, f"{GUIDE} cites paths that do not exist: {missing}"

    def test_cited_laclaugpt_modules_all_exist(self) -> None:
        """The documented infrastructure inventory must exist on disk.

        The guide prints the modules in a fenced block, so match bare
        ``laclaugpt/x.py`` lines as well as backticked ones.
        """
        body = read(GUIDE)
        cited = set(re.findall(r"(?<![`\w])(laclaugpt/[A-Za-z0-9_]+\.py)", body))
        assert len(cited) >= 8, f"expected the module inventory, found {sorted(cited)}"
        missing = sorted(path for path in cited if not (ROOT / path).exists())
        assert not missing, f"cited modules do not exist: {missing}"

    def test_every_documented_module_exists(self) -> None:
        """Catch a module that was renamed while the guide kept citing the old name."""
        body = read(GUIDE)
        cited = set(re.findall(r"(?<![`\w])(laclaugpt/[A-Za-z0-9_]+\.py)", body))
        for path in sorted(cited):
            assert (ROOT / path).is_file(), f"{GUIDE} cites a missing module: {path}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
