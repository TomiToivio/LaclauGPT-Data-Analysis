"""Regression tests for issue #282 periodic-report namespace/status drift."""
from __future__ import annotations

import ast
from pathlib import Path

from laclaugpt_data_analysis.distributed import _MONGO_KINDS, _S3_KINDS, ProjectNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "laclaugpt_data_analysis"


def _literal_namespace_kinds(method: str) -> set[str]:
    kinds: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != method or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                kinds.add(first.value)
    return kinds


def test_literal_namespace_requests_match_allowlists() -> None:
    mongo_requested = _literal_namespace_kinds("mongo_collection")
    s3_requested = _literal_namespace_kinds("s3_key")

    assert mongo_requested <= _MONGO_KINDS, sorted(mongo_requested - _MONGO_KINDS)
    assert s3_requested <= _S3_KINDS, sorted(s3_requested - _S3_KINDS)


def test_phase1_report_uses_canonical_periodic_summary_collection() -> None:
    source = (SRC / "phase1_laskin_report.py").read_text(encoding="utf-8")

    assert 'mongo_collection("periodic_summaries")' in source
    assert 'mongo_collection("periodic_reports")' not in source
    assert ProjectNamespace("ai26").mongo_collection("periodic_summaries") == (
        "ai26__periodic_summaries"
    )


def test_laskin_wrapper_distinguishes_report_failure_from_worker_failure() -> None:
    script = (ROOT / "scripts" / "run_ai26_laskin.sh").read_text(encoding="utf-8")

    assert "WORKER_STATUS=$?" in script
    assert "FINAL_STATUS=$WORKER_STATUS" in script
    assert "FINAL_STATUS=4" in script
    assert "worker_status=$WORKER_STATUS report_status=$REPORT_STATUS" in script
