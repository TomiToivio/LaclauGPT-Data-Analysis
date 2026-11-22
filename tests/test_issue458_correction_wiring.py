"""#458: the wired correction — helpers that decide what to re-ask and what to rewrite.

The policy module's own tests cover verification and the one-correction limit. These
cover the pieces the live discourse stage now uses: which quotes a proposal carries, the
evidence-only prompt, and applying replacements without touching anything else.
"""

from laclaugpt_data_analysis.stages.evidence_policy import (
    apply_corrections,
    build_correction_prompt,
    is_abstention,
    proposal_quotes,
)
from laclaugpt_data_analysis.stages.proposals import DiscourseProposal, DiscursiveElement

SOURCE = "The dam project would displace thousands of reindeer herders near Inari."


def _proposal(*quotes: str) -> DiscourseProposal:
    return DiscourseProposal(
        demands=[DiscursiveElement(label="green_transition", evidence=list(quotes[:1]))],
        frontiers=[DiscursiveElement(label="growth", evidence=list(quotes[1:]))],
    )


def test_proposal_quotes_collects_every_coded_object_and_deduplicates():
    quotes = proposal_quotes(_proposal("a span", "a span", "another span"))
    assert quotes == ["a span", "another span"]


def test_proposal_quotes_ignores_abstentions_so_they_are_never_re_asked():
    quotes = proposal_quotes(_proposal("real span", "no verbatim evidence found"))
    assert quotes == ["real span"]
    assert is_abstention("no verbatim evidence found")


def test_the_prompt_asks_only_for_verbatim_replacements():
    prompt = build_correction_prompt(SOURCE, ["a paraphrase", "another paraphrase"])
    assert "1. a paraphrase" in prompt and "2. another paraphrase" in prompt
    assert "copied character for character" in prompt
    assert SOURCE in prompt, "the correction must quote against the same source item"
    assert "not" in prompt.lower() and "paraphrase" in prompt.lower()


def test_apply_corrections_rewrites_only_the_replaced_quotes():
    proposal = _proposal("a paraphrase", "an untouched span")
    updated, count = apply_corrections(proposal, {"a paraphrase": "thousands of reindeer herders near Inari"})
    assert count == 1
    assert updated.demands[0].evidence == ["thousands of reindeer herders near Inari"]
    assert updated.frontiers[0].evidence == ["an untouched span"], "an untouched quote must survive verbatim"


def test_apply_corrections_leaves_labels_and_other_fields_alone():
    proposal = _proposal("a paraphrase")
    updated, _ = apply_corrections(proposal, {"a paraphrase": "thousands of reindeer herders"})
    assert updated.demands[0].label == "green_transition"


def test_an_empty_replacement_map_is_a_no_op():
    proposal = _proposal("a paraphrase")
    updated, count = apply_corrections(proposal, {})
    assert count == 0 and updated is proposal
