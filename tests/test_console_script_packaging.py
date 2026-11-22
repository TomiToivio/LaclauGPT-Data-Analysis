"""Guard declared console-script module paths during repository cleanup.

This checks packaging paths without importing optional HPC or model dependencies.
Runtime behavior belongs in the corresponding integration tests.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _console_scripts() -> dict[str, str]:
    """Read public CLI targets from the authoritative packaging configuration."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as config_file:
        project = tomllib.load(config_file)["project"]
    return project["scripts"]


@pytest.mark.parametrize("command,target", sorted(_console_scripts().items()))
def test_console_script_module_is_packaged(command: str, target: str) -> None:
    """Every published command must point to a module in the installable src package."""
    module_name, separator, callable_name = target.partition(":")
    assert separator and callable_name.isidentifier(), (
        f"{command} has an invalid console-script target: {target}"
    )
    parts = module_name.split(".")
    assert parts[0] == "laclaugpt_data_analysis", (
        f"{command} points outside the installable package: {target}"
    )
    package_root = REPO_ROOT / "src"
    module_path = package_root.joinpath(*parts).with_suffix(".py")
    package_path = package_root.joinpath(*parts, "__init__.py")
    assert module_path.is_file() or package_path.is_file(), (
        f"{command} references missing Python module {module_name}"
    )


def test_console_script_names_are_unique() -> None:
    """Keep the published command set well-defined in project metadata."""
    scripts = _console_scripts()
    assert scripts, "No console scripts found in pyproject.toml"
    assert all(name.strip() == name for name in scripts)
