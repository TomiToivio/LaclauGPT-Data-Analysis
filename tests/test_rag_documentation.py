"""The retrieval layer's public contracts must stay documented.

`rag.py` mixes a handful of load-bearing contracts (audit provenance, the advisory status of
retrieved material, the refusal to guess a backend) with a long tail of one-line stubs. Documenting
the stubs would be noise; leaving the contracts undocumented is how a later reader concludes that a
retrieval score is evidence. This test pins what must keep a docstring -- the module and every
public class and module-level function -- without dictating prose for the stubs.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "src/laclaugpt_data_analysis/rag.py"


@pytest.fixture(scope="module")
def tree() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def test_module_docstring_states_the_advisory_contract(tree: ast.Module):
    doc = ast.get_docstring(tree) or ""
    assert "advisory" in doc.lower(), "the module docstring must say retrieval is consultative"
    assert "evidence" in doc.lower(), "it must distinguish a retrieved item from evidence"


def test_every_public_class_and_function_is_documented(tree: ast.Module):
    undocumented = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
        and not node.name.startswith("_")
        and not ast.get_docstring(node)
    ]
    assert not undocumented, f"public contracts without a docstring: {undocumented}"


def test_the_audit_and_failure_paths_explain_themselves(tree: ast.Module):
    """Two docstrings carry the reasoning that keeps the layer honest; they must not be emptied."""
    wanted = {"RetrievalAudit": "provenance", "failed_context": "raising"}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in wanted:
            doc = (ast.get_docstring(node) or "").lower()
            assert wanted[node.name] in doc, f"{node.name} lost the reason it exists"
