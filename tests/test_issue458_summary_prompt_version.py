"""#458: AI26 summary receives a versioned verbatim-text instruction without changing EP24."""
from pathlib import Path

from laclaugpt_data_analysis.prompt_library import load_prompt


def test_ai26_summary_v3_is_versioned_and_preserves_legacy_prompt():
    original = load_prompt("multimodal.summary_analysis", version="v2")
    updated = load_prompt("multimodal.summary_analysis", version="v3")
    assert original.sha256 != updated.sha256
    assert "contiguous verbatim source span" in updated.text
    assert "contiguous verbatim source span" not in original.text


def test_summary_stage_only_selects_v3_for_ai26():
    path = Path(__file__).resolve().parents[1] / "src/laclaugpt_data_analysis/stages/summary.py"
    source = path.read_text(encoding="utf-8")
    assert 'version="v3" if project_profile.casefold() == "ai26" else "v2"' in source
