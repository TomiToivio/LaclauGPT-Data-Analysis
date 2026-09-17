"""Regression coverage for the frozen-manifest re-freeze problem (issue #121).

A scheduled analysis run must not be stopped by a docs-only, CI-only or
test-only merge. It must still stop when the analysed source actually changes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from laclaugpt_data_analysis.distributed_worker import (
    FrozenRunManifest,
    _source_tree_sha256,
)


def _manifest(**overrides) -> FrozenRunManifest:
    base = dict(
        project_id="ai26",
        run_id="ai26-distributed-001",
        schema_version="1.2.0",
        config_sha256="a" * 64,
        codebook_sha256="b" * 64,
        model="gemma4:12b",
        public_git_sha="c" * 40,
    )
    base.update(overrides)
    return FrozenRunManifest(**base)


# --------------------------------------------------------------- the hash


def test_source_tree_hash_is_deterministic() -> None:
    assert _source_tree_sha256() == _source_tree_sha256()


def test_source_tree_hash_is_a_sha256_hex_digest() -> None:
    value = _source_tree_sha256()
    assert len(value) == 64
    assert all(c in "0123456789abcdef" for c in value)


def test_source_tree_hash_ignores_non_source_files(tmp_path: Path) -> None:
    """Docs, tests and CI changes must not alter the analysed-code identity."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "module.py").write_text("x = 1\n", encoding="utf-8")
    baseline = _source_tree_sha256(tmp_path)

    (tmp_path / "README.md").write_text("# changed docs\n", encoding="utf-8")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.yml").write_text("jobs: {}\n", encoding="utf-8")

    assert _source_tree_sha256(tmp_path) == baseline


def test_source_tree_hash_changes_when_source_changes(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    target = src / "module.py"
    target.write_text("x = 1\n", encoding="utf-8")
    baseline = _source_tree_sha256(tmp_path)

    target.write_text("x = 2\n", encoding="utf-8")
    assert _source_tree_sha256(tmp_path) != baseline


def test_source_tree_hash_detects_added_and_removed_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("a = 1\n", encoding="utf-8")
    baseline = _source_tree_sha256(tmp_path)

    (src / "b.py").write_text("b = 1\n", encoding="utf-8")
    with_added = _source_tree_sha256(tmp_path)
    assert with_added != baseline

    (src / "b.py").unlink()
    assert _source_tree_sha256(tmp_path) == baseline


# --------------------------------------------------------------- the manifest


def test_manifest_field_is_optional_for_backwards_compatibility() -> None:
    """Manifests written before this field existed must still load."""
    manifest = _manifest()
    assert manifest.source_tree_sha256 == ""


def test_manifest_load_ignores_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "run-manifest.json"
    path.write_text(
        '{"project_id":"ai26","run_id":"r","schema_version":"1.2.0",'
        '"config_sha256":"a","codebook_sha256":"b","model":"m",'
        '"public_git_sha":"c","some_future_field":1}',
        encoding="utf-8",
    )
    manifest = FrozenRunManifest.load(path)
    assert manifest.project_id == "ai26"
    assert manifest.source_tree_sha256 == ""


def test_manifest_load_reads_the_tree_hash(tmp_path: Path) -> None:
    path = tmp_path / "run-manifest.json"
    path.write_text(
        '{"project_id":"ai26","run_id":"r","schema_version":"1.2.0",'
        '"config_sha256":"a","codebook_sha256":"b","model":"m",'
        '"public_git_sha":"c","source_tree_sha256":"deadbeef"}',
        encoding="utf-8",
    )
    assert FrozenRunManifest.load(path).source_tree_sha256 == "deadbeef"


# --------------------------------------------------------------- validation


def _binding_with(manifest: FrozenRunManifest):
    from laclaugpt_data_analysis.distributed_worker import WorkerBinding

    return WorkerBinding(
        manifest=manifest,
        manifest_path=Path("/nonexistent/run-manifest.json"),
        private_config=Path("/nonexistent/analysis.json"),
        codebook=Path("/nonexistent/codebook.json"),
        worker_id="test-worker",
    )


def test_matching_tree_hash_passes_even_when_commit_differs() -> None:
    """The #121 case: same analysed code, different commit."""
    manifest = _manifest(
        public_git_sha="0" * 40,
        source_tree_sha256=_source_tree_sha256(),
    )
    _binding_with(manifest).validate_runtime_code()


def test_changed_tree_hash_fails_with_a_re_freeze_hint() -> None:
    manifest = _manifest(source_tree_sha256="f" * 64)
    with pytest.raises(ValueError, match="source tree has changed"):
        _binding_with(manifest).validate_runtime_code()


def test_changed_tree_error_names_the_re_freeze_command() -> None:
    manifest = _manifest(source_tree_sha256="f" * 64)
    with pytest.raises(ValueError, match="laclaugpt-freeze-ai26"):
        _binding_with(manifest).validate_runtime_code()


def test_legacy_manifest_still_uses_the_strict_commit_check() -> None:
    """Without a tree hash the original guarantee is preserved, not dropped."""
    manifest = _manifest(source_tree_sha256="")
    with pytest.raises(ValueError) as excinfo:
        _binding_with(manifest).validate_runtime_code()
    message = str(excinfo.value)
    assert "public Git SHA does not match" in message or "cannot determine" in message


def test_legacy_commit_mismatch_message_also_hints_re_freeze() -> None:
    manifest = _manifest(public_git_sha="d" * 40, source_tree_sha256="")
    with pytest.raises(ValueError, match="laclaugpt-freeze-ai26"):
        _binding_with(manifest).validate_runtime_code()
