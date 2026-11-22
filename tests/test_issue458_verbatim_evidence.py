"""#458 / D6: verbatim evidence, one bounded correction, then abstention.

The measured problem: 62 051 evidence items, 27 044 (43.6 %) locatable, 35.2 % of
sampled non-verbatim items being paraphrase. These tests pin the policy that the
approved option (a) requires, and the properties the issue insists must survive it:
`exact` and the counts stay comparable, no coded object is lost, and an abstention
never becomes a citation.
"""

from laclaugpt_data_analysis.stages.evidence_policy import (
    MAX_CORRECTIONS,
    EvidenceVerification,
    apply_verbatim_policy,
    verify_quotes,
)

SOURCE = "The dam project would displace thousands of reindeer herders near Inari."


def test_an_exact_quotation_is_accepted():
    ok, bad = verify_quotes(SOURCE, ["The dam project would displace thousands"])
    assert ok == ["The dam project would displace thousands"] and bad == []


def test_whitespace_and_unicode_normalisation_still_matches():
    ok, bad = verify_quotes(SOURCE, ["  The   dam project\nwould displace  thousands "])
    assert ok and not bad


def test_an_elided_span_is_not_a_verbatim_quotation():
    ok, bad = verify_quotes(SOURCE, ["The dam project ... near Inari."])
    assert not ok and len(bad) == 1


def test_a_paraphrase_is_rejected_rather_than_rewritten():
    ok, bad = verify_quotes(SOURCE, ["a dam that will force herders to move"])
    assert not ok and bad == ["a dam that will force herders to move"]


def test_a_translation_is_not_verbatim_even_when_faithful():
    ok, bad = verify_quotes(SOURCE, ["Pato hankkeesta karkottaisi tuhansia poronhoitajia"])
    assert not ok, "a faithful translation is not a source span"


def test_empty_source_yields_no_citation_instead_of_a_guess():
    ok, bad = verify_quotes("", ["anything at all"])
    assert not ok and bad == ["anything at all"]


def test_an_abstention_marker_is_neither_accepted_nor_counted_as_unlocatable():
    ok, bad = verify_quotes(SOURCE, ["no verbatim evidence found"])
    assert not ok and not bad


def test_one_correction_resolves_the_quote_on_the_same_source():
    calls = []
    def reprompt(failed):
        calls.append(failed)
        return ["thousands of reindeer herders near Inari"]
    outcome = apply_verbatim_policy(SOURCE, ["herders forced out"], reprompt=reprompt)
    assert outcome.status == "verified"
    assert outcome.accepted == ["thousands of reindeer herders near Inari"]
    assert outcome.corrections_attempted == 1 and outcome.corrections_resolved == 1
    assert len(calls) == 1


def test_a_failed_correction_abstains_and_keeps_the_object():
    outcome = apply_verbatim_policy(SOURCE, ["herders forced out"], reprompt=lambda f: ["still a paraphrase"])
    assert outcome.status == "abstained_unlocatable"
    assert outcome.corrections_attempted == 1 and outcome.corrections_resolved == 0
    assert outcome.telemetry()["accepted"] == 0


def test_the_correction_is_never_attempted_more_than_once():
    calls = []
    def reprompt(failed):
        calls.append(failed)
        return ["still wrong"]
    apply_verbatim_policy(SOURCE, ["wrong"], reprompt=reprompt)
    assert len(calls) == 1 and MAX_CORRECTIONS == 1


def test_no_reprompt_means_no_correction_attempt():
    outcome = apply_verbatim_policy(SOURCE, ["wrong"])
    assert outcome.corrections_attempted == 0
    assert outcome.status == "abstained_unlocatable"


def test_an_object_with_no_quotes_reports_no_evidence_not_abstention():
    outcome = apply_verbatim_policy(SOURCE, [])
    assert outcome.status == "no_evidence"
    assert outcome.telemetry()["abstained"] is False


def test_telemetry_is_attributable_per_run():
    outcome = EvidenceVerification(accepted=["a"], unlocatable=[])
    assert outcome.telemetry() == {
        "status": "verified", "accepted": 1, "unlocatable": 0, "abstained": False,
        "corrections_attempted": 0, "corrections_resolved": 0, "corrections_failed": 0,
    }
