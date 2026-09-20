from __future__ import annotations

import ast
import pathlib
import tomllib

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "legacy_phase1_inventory.yaml"

PUHTI_MODULES = {
    "puhti_frame",
    "puhti_summary",
    "puhti_populism",
    "puhti_preprocess",
    "puhti_postprocess",
}


def _inventory() -> dict:
    return yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))


def _path_exists(value: str) -> bool:
    return (ROOT / value.rstrip("/")).exists()


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


def test_inventory_is_complete_and_non_destructive() -> None:
    data = _inventory()
    assert data["issue"] == 224
    assert data["phase"] == 1
    assert data["policy"]["deletion_in_this_issue"] is False

    decisions = {item["decision"] for item in data["items"]}
    assert {"keep", "adapt", "delete_after_replacement"} <= decisions

    for item in data["items"]:
        assert _path_exists(item["path"]), item["path"]
        assert item["deletion_allowed"] is False
        for test_path in item.get("regression_tests", []):
            assert _path_exists(test_path), test_path


def test_delete_after_replacement_candidates_have_regression_coverage() -> None:
    data = _inventory()
    by_path = {item["path"]: item for item in data["items"]}
    candidates = data["delete_after_replacement_candidates"]

    assert candidates
    for path in candidates:
        item = by_path[path]
        assert item["state"] == "quarantined"
        assert item["decision"] == "delete_after_replacement"
        assert item["deletion_allowed"] is False
        assert item["regression_tests"]


def test_packaged_entry_points_do_not_activate_puhti_scripts() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = project["project"].get("scripts", {})

    assert scripts
    assert all("puhti_" not in target for target in scripts.values())
    assert all(not target.startswith("laclaugpt.") for target in scripts.values())


def test_canonical_runtime_does_not_import_legacy_puhti_modules() -> None:
    source_root = ROOT / "src" / "laclaugpt_data_analysis"

    offenders: list[str] = []
    for path in source_root.rglob("*.py"):
        for imported in _legacy_puhti_imports(path):
            offenders.append(f"{path.relative_to(ROOT)} -> {imported}")

    assert offenders == []
