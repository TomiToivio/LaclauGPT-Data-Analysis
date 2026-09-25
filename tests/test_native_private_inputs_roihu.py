"""Issue #243/#245: Roihu must not depend on legacy private submodules.

Synthetic/static checks only: do not read private research data in public CI.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ep24_launcher_only_reads_canonical_private_sources():
    script = (ROOT / "scripts/ep24/ep24_roihu_reprocess.sbatch").read_text()
    assert "promote_legacy_inputs.sh" in script
    assert "git submodule" not in script
    assert "migrate_from_legacy.sh" not in script
    for name in (
        "research_notes.xlsx", "entities.xlsx", "themes.xlsx",
        "ep24_finland_dashboard_9_1_2026.csv",
        "ep24_poland_dashboard_9_1_2026.csv",
    ):
        assert name in script
    assert "ep24_common_private.json" in script


def test_hungary26_launcher_only_reads_canonical_private_sources():
    script = (ROOT / "scripts/hungary26/hungary26_roihu_test.sbatch").read_text()
    assert "promote_legacy_inputs.sh" in script
    assert "git submodule" not in script
    assert "migrate_from_legacy.py" not in script
    assert "source/${workbook}" in script
    assert "hungary2026_instagram.xlsx" in script
    assert "hungary2026_tiktok.xlsx" in script


def test_phase0_minimal_requirements_not_touched():
    requirements = (ROOT / "laclaugpt/requirements.txt").read_text().lower()
    assert "faster-whisper" not in requirements
    assert "openpyxl" not in requirements
