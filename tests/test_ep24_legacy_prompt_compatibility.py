from pathlib import Path

from laclaugpt_data_analysis.prompt_library import load_prompt


def test_ep24_v2_frame_prompt_preserves_legacy_categories() -> None:
    prompt = load_prompt("ep24.frame_analysis", version="v2")
    text = prompt.text.lower()
    for category in (
        "framing",
        "visual elements",
        "activity",
        "color scheme",
        "objects",
        "subjects",
        "screen-recording",
        "pets",
    ):
        assert category in text
    assert "do not infer" in text
    assert "uncertainty" in text


def test_ep24_v2_summary_prompt_preserves_all_nine_legacy_categories() -> None:
    prompt = load_prompt("ep24.summary_analysis", version="v2")
    text = prompt.text.lower()
    for category in (
        "narrative construction",
        "political classification",
        "difficult language",
        "key political topics",
        "political entities",
        "sentiment analysis",
        "political populism",
        "social contract",
        "grievance politics",
    ):
        assert category in text
    assert "multimodal evidence audit" in text
    assert "not_evidenced" in text


def test_ep24_v2_laclau_prompt_preserves_legacy_formula_depth() -> None:
    prompt = load_prompt("ep24.laclau_analysis", version="v2")
    text = prompt.text.lower()
    for concept in (
        "us / the people",
        "chains of equivalence",
        "frontier / them",
        "empty signifier",
        "affective polarisation",
        "formula of populism",
        "no supported populist articulation",
    ):
        assert concept in text


def test_ep24_runner_selects_legacy_complete_v2_prompts() -> None:
    runner = Path("scripts/ep24/run_country_reprocess.sh").read_text(encoding="utf-8")
    assert 'EP24_FRAME_PROMPT_ID="ep24.frame_analysis:v2"' in runner
    assert 'EP24_SUMMARY_PROMPT_ID="ep24.summary_analysis:v2"' in runner
    assert 'EP24_LACLAU_PROMPT_ID="ep24.laclau_analysis:v2"' in runner
    assert "EP24_LEGACY_PROMPT_ARCHIVE" in runner
