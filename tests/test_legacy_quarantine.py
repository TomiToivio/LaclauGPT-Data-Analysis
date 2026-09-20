from __future__ import annotations

import pathlib
import re
import tomllib


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "laclaugpt_data_analysis"
AUDIT = ROOT / "docs" / "LEGACY_PHASE1_AUDIT.md"

PUHTI_MODULES = {
    "puhti_frame",
    "puhti_summary",
    "puhti_populism",
    "puhti_preprocess",
    "puhti_postprocess",
}


def test_active_runtime_does_not_import_quarantined_puhti_modules() -> None:
    import_pattern = re.compile(
        r"^\s*(?:from|import)\s+(?:laclaugpt\.)?(puhti_[A-Za-z0-9_]*)\b",
        re.MULTILINE,
    )
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in import_pattern.finditer(text):
            if match.group(1) in PUHTI_MODULES:
                offenders.append(f"{path.relative_to(ROOT)} -> {match.group(1)}")
    assert offenders == [], "active runtime imports quarantined legacy code: " + ", ".join(offenders)


def test_console_entry_points_do_not_target_quarantined_legacy_scripts() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = config.get("project", {}).get("scripts", {})
    offenders = {
        name: target
        for name, target in scripts.items()
        if "puhti_" in target or target.startswith("laclaugpt.")
    }
    assert offenders == {}


def test_audit_inventory_names_every_puhti_candidate_and_all_three_decisions() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    for module in sorted(PUHTI_MODULES):
        assert f"laclaugpt/{module}.py" in text
    assert "KEEP / QUARANTINE" in text
    assert "ADAPT / CANONICALIZED" in text
    assert "DELETE AFTER REPLACEMENT" in text
