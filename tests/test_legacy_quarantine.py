from __future__ import annotations

import ast
import pathlib
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


def _legacy_puhti_imports(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name in PUHTI_MODULES:
                    offenders.append(name)
                    continue
                for module in PUHTI_MODULES:
                    if name == f"laclaugpt.{module}" or name.startswith(f"laclaugpt.{module}."):
                        offenders.append(name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in PUHTI_MODULES:
                offenders.append(module)
                continue

            for legacy_module in PUHTI_MODULES:
                if module == f"laclaugpt.{legacy_module}" or module.startswith(
                    f"laclaugpt.{legacy_module}."
                ):
                    offenders.append(module)

            if module == "laclaugpt":
                for alias in node.names:
                    if alias.name in PUHTI_MODULES:
                        offenders.append(f"laclaugpt.{alias.name}")

    return offenders


def test_active_runtime_does_not_import_quarantined_puhti_modules() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        for imported in _legacy_puhti_imports(path):
            offenders.append(f"{path.relative_to(ROOT)} -> {imported}")
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
