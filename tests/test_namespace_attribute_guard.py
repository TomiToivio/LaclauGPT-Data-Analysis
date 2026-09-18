"""Guard against references to namespace helpers that do not exist.

Issue #153 direction 3: a ``namespace.<method>`` reference that no class defines
should not be able to land again. The original defect was a hard
``AttributeError`` at run time on the live distributed path, invisible to CI
because the calling function had no coverage.

This module-level check walks the repository's own source with ``ast`` and
asserts that every attribute accessed on a value *known to be* a
``ProjectNamespace`` (i.e. ``settings.distributed_namespace`` /
``ProjectNamespace(...)`` bound to a local name) is actually defined by the class.

It is deliberately static and offline: no Redis, no network, no import of the
module under test.
"""
from __future__ import annotations

import ast
from pathlib import Path

from laclaugpt_data_analysis.distributed import ProjectNamespace

SRC = Path(__file__).resolve().parents[1] / "src"

_NAMESPACE_METHODS = {name for name in dir(ProjectNamespace) if not name.startswith("_")}
_NAMESPACE_PROPERTIES = {"redis_base"}


def _namespace_attributes_used(path: Path) -> list[tuple[int, str]]:
    """Return every ``<namespace>.<attr>`` access in one source file.

    A local name counts as a namespace if it was assigned from
    ``...distributed_namespace`` or from a ``ProjectNamespace(...)`` call.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    namespace_names: set[str] = set()

    for node in ast.walk(tree):
        # ``namespace = settings.distributed_namespace``
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute):
            if node.value.attr == "distributed_namespace":
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        namespace_names.add(target.id)
        # ``namespace = ProjectNamespace("ai26")``
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            if (isinstance(func, ast.Name) and func.id == "ProjectNamespace") or (
                isinstance(func, ast.Attribute) and func.attr == "ProjectNamespace"
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        namespace_names.add(target.id)

    used: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in namespace_names:
                used.append((node.lineno, node.attr))
    return used


def _project_source_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def test_every_namespace_attribute_used_is_defined() -> None:
    """The regression guard for issue #153.

    Before the fix, ``task_queue.py`` called ``namespace.redis_stream``,
    ``redis_group`` and ``redis_heartbeat``; none existed on ``ProjectNamespace``
    and the class has no ``__getattr__`` fallback, so each was a hard
    ``AttributeError`` on the live path.
    """
    known = _NAMESPACE_METHODS | _NAMESPACE_PROPERTIES
    offenders: list[str] = []
    for path in _project_source_files():
        for lineno, attr in _namespace_attributes_used(path):
            if attr not in known:
                offenders.append(f"{path.relative_to(SRC.parent)}:{lineno} namespace.{attr}")
    assert not offenders, (
        "namespace attribute(s) not defined on ProjectNamespace:\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_detects_a_missing_helper() -> None:
    """Prove the guard actually fires — do not just observe it pass."""
    assert "redis_stream" not in _NAMESPACE_METHODS
    assert "redis_group" not in _NAMESPACE_METHODS
    assert "redis_heartbeat" not in _NAMESPACE_METHODS
    # ...and that the helpers the fix does use ARE defined.
    for present in ("stream_key", "redis_key", "worker_key"):
        assert present in _NAMESPACE_METHODS


def test_guard_scans_a_real_file(tmp_path) -> None:
    """A synthetic file using a bogus helper must be reported."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "def f(settings):\n"
        "    namespace = settings.distributed_namespace\n"
        "    return namespace.redis_stream('analysis')\n",
        encoding="utf-8",
    )
    used = dict((attr, lineno) for lineno, attr in _namespace_attributes_used(sample))
    assert "redis_stream" in used
    assert "redis_stream" not in (_NAMESPACE_METHODS | _NAMESPACE_PROPERTIES)
