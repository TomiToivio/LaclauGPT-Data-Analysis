"""Freeze the private AI26 runtime inputs for a distributed run.

A distributed run is only reproducible if the exact private inputs are pinned by
hash before any worker starts. This tool builds that boundary:

  1. merge the public AI26 codebook with an optional private overlay;
  2. validate the merged codebook;
  3. write the effective codebook into the private runtime directory;
  4. compute the SHA-256 of the effective codebook and the private analysis
     configuration;
  5. write ``run-manifest.json`` binding project, run, schema, model and the
     public Data-Analysis Git revision together.

The outputs live below the private root and are never committed. Secrets are
never read or written here — only the two configuration files and their hashes.

Usage:

    laclaugpt-freeze-ai26 \\
      --private-root /path/to/private-root/analysis/ai26 \\
      --public-codebook codebooks/public/ai26_v2.yaml \\
      --private-overlay /path/to/private_overlay.yaml \\
      --analysis-config /path/to/analysis.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .canonical import SCHEMA_VERSION
from .codebooks import load_codebook, merge_codebooks

DEFAULT_MODEL = "gemma4:12b"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def source_tree_sha256() -> str:
    """Hash the analysed source tree so docs/CI merges do not stale a run.

    Shares the definition used by the worker's validator, so a freeze and a
    validation can never disagree about what "the analysed code" means.
    """
    from .distributed_worker import _source_tree_sha256

    return _source_tree_sha256(_repo_root())


def resolve_public_git_sha(explicit: str = "") -> str:
    """Resolve the public Data-Analysis revision, or fail rather than guess."""
    if explicit.strip():
        return explicit.strip()
    env_value = os.environ.get("LACLAUGPT_PUBLIC_GIT_SHA", "").strip()
    if env_value:
        return env_value
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(
            "cannot determine the public Git SHA; pass --public-git-sha or set "
            "LACLAUGPT_PUBLIC_GIT_SHA"
        ) from exc
    sha = completed.stdout.strip()
    if not sha:
        raise ValueError("cannot determine the public Git SHA")
    return sha


def _inside(root: Path, path: Path) -> Path:
    """Resolve ``path`` and require it to live below ``root`` (fail closed)."""
    resolved_root = root.expanduser().resolve()
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"path must live inside {resolved_root}: {resolved}") from exc
    return resolved


def build_effective_codebook(
    *,
    public_codebook: str | Path,
    private_overlay: str | Path | None = None,
    output: str | Path,
) -> Path:
    """Merge public + optional private codebook and write the effective result."""
    books = [load_codebook(public_codebook)]
    if private_overlay is not None:
        books.append(load_codebook(private_overlay))
    effective = merge_codebooks(books, codebook_id="ai26-effective")
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(effective.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def write_run_manifest(
    *,
    private_root: str | Path,
    analysis_config: str | Path,
    codebook: str | Path,
    project_id: str = "ai26",
    run_id: str,
    model: str = DEFAULT_MODEL,
    public_git_sha: str = "",
) -> dict[str, Any]:
    """Write ``run-manifest.json`` binding the frozen private inputs."""
    root = Path(private_root)
    config_path = _inside(root, Path(analysis_config))
    codebook_path = _inside(root, Path(codebook))
    if not config_path.is_file():
        raise ValueError(f"analysis config does not exist: {config_path}")
    if not codebook_path.is_file():
        raise ValueError(f"effective codebook does not exist: {codebook_path}")

    manifest = {
        "project_id": project_id,
        "run_id": run_id,
        "schema_version": SCHEMA_VERSION,
        "config_sha256": _sha256_file(config_path),
        "codebook_sha256": _sha256_file(codebook_path),
        "model": model,
        "public_git_sha": resolve_public_git_sha(public_git_sha),
        "source_tree_sha256": source_tree_sha256(),
    }
    manifest_path = root / "run-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze private AI26 runtime inputs for a distributed run"
    )
    parser.add_argument("--private-root", required=True)
    parser.add_argument("--public-codebook", required=True)
    parser.add_argument("--private-overlay")
    parser.add_argument(
        "--analysis-config",
        required=True,
        help="private analysis configuration file to hash and bind",
    )
    parser.add_argument("--codebook-output")
    parser.add_argument("--project-id", default="ai26")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--public-git-sha", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.private_root)
    root.mkdir(parents=True, exist_ok=True)

    # Keep every written artifact below the declared private root.
    codebook_output = Path(args.codebook_output) if args.codebook_output else (
        root / "codebook.json"
    )
    _inside(root, codebook_output)

    build_effective_codebook(
        public_codebook=args.public_codebook,
        private_overlay=args.private_overlay,
        output=codebook_output,
    )
    manifest = write_run_manifest(
        private_root=root,
        analysis_config=args.analysis_config,
        codebook=codebook_output,
        project_id=args.project_id,
        run_id=args.run_id,
        model=args.model,
        public_git_sha=args.public_git_sha,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
