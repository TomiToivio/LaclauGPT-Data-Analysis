from laclaugpt_discourse import PROMPT_VERSION, SYSTEM_PROMPT


def test_prompt_forbids_populism_classification():
    lowered = SYSTEM_PROMPT.lower()
    assert "never output populism true/false" in lowered
    assert "us/frontier/affect are candidate structures" in lowered


def test_prompt_keeps_affect_distinct_from_sentiment():
    lowered = SYSTEM_PROMPT.lower()
    assert "sentiment is not affective investment" in lowered
    assert "disagreement or negative sentiment is not automatically antagonism" in lowered


def test_prompt_declares_required_phase0_fields():
    lowered = SYSTEM_PROMPT.lower()
    for key in (
        "signifiers",
        "articulations",
        "demands",
        "collective_subjects",
        "frontiers",
        "affects",
        "formation_evidence",
        "counter_evidence",
        "uncertainty_notes",
    ):
        assert key in lowered


def test_prompt_version_is_explicit():
    # The version identifies the discourse prompt contract and is expected to be bumped
    # when that contract changes (v2 = bounded/truncated input). Assert the shape rather
    # than one frozen literal, so a deliberate bump does not turn CI red.
    assert isinstance(PROMPT_VERSION, str)
    assert PROMPT_VERSION.startswith("ai26-phase0-discourse-v")
    suffix = PROMPT_VERSION.removeprefix("ai26-phase0-discourse-v")
    assert suffix.isdigit() and int(suffix) >= 1
