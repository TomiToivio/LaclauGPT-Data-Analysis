from __future__ import annotations

import pathlib
import re
import tomllib

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "legacy_phase1_inventory.yaml"


def _inventory() -> dict:
    return yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))


def _path_exists(value: str) -> bool:
    return (ROOT / value.rstrip("/")).exists()


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
    legacy_import = re.compile(
        r"^\s*(?:"
        r"from\s+laclaugpt(?:\.|\s+import\s+).*puhti_|"
        r"import\s+laclaugpt\.puhti_|"
        r"from\s+puhti_[A-Za-z0-9_]*\s+import\s+|"
        r"import\s+puhti_[A-Za-z0-9_]*"
        r")",
        re.MULTILINE,
    )

    offenders = []
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if legacy_import.search(text):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
