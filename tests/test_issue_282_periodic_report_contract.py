from __future__ import annotations

import ast
from pathlib import Path

from laclaugpt_data_analysis.distributed import (
    _MONGO_KINDS,
    _S3_KINDS,
    ProjectNamespace,
)


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "laclaugpt_data_analysis"


def _literal_namespace_kinds(method: str) -> set[str]:
    kinds: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != method:
                continue
            if not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                kinds.add(first.value)
    return kinds


def test_all_literal_namespace_kinds_are_allowlisted() -> None:
    mongo_kinds = _literal_namespace_kinds("mongo_collection")
    s3_kinds = _literal_namespace_kinds("s3_key")

    assert mongo_kinds <= _MONGO_KINDS, (
        f"MongoDB kinds used by package but absent from allowlist: "
        f"{sorted(mongo_kinds - _MONGO_KINDS)}"
    )
    assert s3_kinds <= _S3_KINDS, (
        f"S3 kinds used by package but absent from allowlist: "
        f"{sorted(s3_kinds - _S3_KINDS)}"
    )


def test_phase1_report_uses_periodic_summaries_contract() -> None:
    source = (
        SRC / "phase1_laskin_report.py"
    ).read_text(encoding="utf-8")

    assert 'mongo_collection("periodic_summaries")' in source
    assert 'mongo_collection("periodic_reports")' not in source
    assert (
        ProjectNamespace("ai26").mongo_collection("periodic_summaries")
        == "ai26__periodic_summaries"
    )


def test_laskin_wrapper_separates_worker_and_report_status() -> None:
    script = (ROOT / "scripts" / "run_ai26_laskin.sh").read_text(encoding="utf-8")

    assert "WORKER_STATUS=$?" in script
    assert 'if [[ "$WORKER_STATUS" -eq 0 ]]; then' in script
    assert "STATUS=4" in script
    assert "worker_status=$WORKER_STATUS report_status=$REPORT_STATUS status=$STATUS" in script
    assert "STATUS=$REPORT_STATUS" not in script
