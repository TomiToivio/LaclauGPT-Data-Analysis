"""The analytical-core modules keep their public surface documented (#548).

The burn-down in #548 documented 59 public names across six modules. Without a guard the next
refactor quietly adds an undocumented one and the measurement that motivated the work becomes
stale -- the same failure mode the documentation index had before it was tested.

Scope is deliberate: top-level public classes and functions only. Methods are excluded because a
well-named `write`/`read` on a store does not need "writes the object", which is the restating the
issue asks us to avoid.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

MODULES = (
    "dna_statement_coding",
    "social_semiotic",
    "distributed",
    "phase1_laskin",
    "memory/models",
    "knowledge_graph",
)
PACKAGE = Path(__file__).resolve().parents[1] / "src/laclaugpt_data_analysis"


def public_nodes(tree: ast.Module) -> list[ast.ClassDef | ast.FunctionDef]:
    return [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef | ast.FunctionDef) and not node.name.startswith("_")
    ]


@pytest.mark.parametrize("module", MODULES)
def test_public_surface_is_documented(module: str):
    path = PACKAGE / f"{module}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    missing = [node.name for node in public_nodes(tree) if not ast.get_docstring(node)]
    assert not missing, f"{module}.py has undocumented public names: {missing}"


@pytest.mark.parametrize("module", MODULES)
def test_module_docstring_exists(module: str):
    tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
    assert ast.get_docstring(tree), f"{module}.py needs a module docstring (purpose + boundary)"
