"""Run manifest freeze/load for the distributed AI26 test.

The manifest (schemas/distributed-run.schema.json in the umbrella repo) freezes
model, codebook/config hashes, canonical schema version and public git SHAs so
that every worker in one run analyses with identical semantics. Workers refuse
to process when their local state does not match the frozen manifest.

Private AI26 configuration is loaded at runtime from
``LACLAUGPT_PRIVATE_CONFIG_DIR`` and is represented in provenance **only by
SHA-256 hashes** — never paths, payloads, source lists or credentials.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .distributed_env import TEST_MODEL
from .schema_version import SCHEMA_VERSION

MANIFEST_SCHEMA_VERSION = "1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def discover_codebook(config_dir: Path) -> Path:
    """Locate the canonical AI26 codebook inside the private config directory.

    Accepted layouts (private repository conventions): a ``codebooks/``
    subdirectory or top-level ``*codebook*`` files. Fails closed when absent.
    """
    candidates: list[Path] = []
    codebooks_dir = config_dir / "codebooks"
    if codebooks_dir.is_dir():
        candidates.extend(sorted(codebooks_dir.glob("*.yaml")))
        candidates.extend(sorted(codebooks_dir.glob("*.yml")))
        candidates.extend(sorted(codebooks_dir.glob("*.md")))
    candidates.extend(sorted(config_dir.glob("*codebook*")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "no canonical codebook found in the private config directory; "
        "refusing to run without the AI26 codebook (fail closed)"
    )


def discover_settings(config_dir: Path) -> Path:
    """Locate the effective AI26 settings document (project YAML) fail-closed."""
    candidates: list[Path] = []
    projects_dir = config_dir / "projects"
    if projects_dir.is_dir():
        candidates.extend(sorted(projects_dir.glob("ai26.yaml")))
    candidates.extend(sorted(config_dir.glob("ai26*.yaml")))
    candidates.extend(sorted(config_dir.glob("*settings*.yaml")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "no AI26 project settings found in the private config directory; "
        "refusing to run (fail closed)"
    )


def _git_sha(path: Path, ref: str = "HEAD") -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def freeze_manifest(
    *,
    run_id: str,
    project_id: str,
    worker_id: str,
    private_config_dir: Path,
    repo_root: Path | None = None,
    test_run: bool = True,
    max_records_per_arena: int | None = None,
    model: str = TEST_MODEL,
) -> dict[str, Any]:
    """Build the frozen run manifest from local state. No secrets are read."""
    codebook = discover_codebook(private_config_dir)
    settings = discover_settings(private_config_dir)
    root = repo_root or Path(__file__).resolve().parents[3]
    shas: dict[str, str | None] = {"data-analysis": _git_sha(Path(__file__).resolve().parents[2])}
    if (root / ".gitmodules").exists():
        shas["laclaugpt"] = _git_sha(root)
    else:
        shas["laclaugpt"] = None

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "project_id": project_id,
        "created_at": datetime.now(UTC).isoformat(),
        "test_run": test_run,
        "model": {
            "text": model,
            "ollama_mode": "local",
            "allow_cloud_fallback": False,
            "endpoint_policy": "per-host",
        },
        "config_hashes": {
            "codebook": sha256_file(codebook),
            "analysis_settings": sha256_file(settings),
            "schema_version": SCHEMA_VERSION,
        },
        "identity": {
            "git_shas": shas,
            "worker_id": worker_id,
        },
    }
    if max_records_per_arena is not None:
        manifest["test_selection"] = {
            "source": "private",
            "max_records_per_arena": int(max_records_per_arena),
        }
    return manifest


def manifest_mismatches(
    manifest: dict[str, Any],
    *,
    model: str = TEST_MODEL,
    private_config_dir: Path,
    schema_version: str = SCHEMA_VERSION,
) -> list[str]:
    """Return reasons a worker must refuse to join the frozen run."""
    errors: list[str] = []
    manifest_model = str(manifest.get("model", {}).get("text", ""))
    if manifest_model and manifest_model != model:
        errors.append(f"model mismatch: run froze {manifest_model!r}, worker has {model!r}")
    if manifest.get("model", {}).get("allow_cloud_fallback") is not False:
        errors.append("run manifest must forbid cloud fallback")
    if manifest.get("model", {}).get("ollama_mode") != "local":
        errors.append("run manifest must pin ollama_mode=local")
    hashes = manifest.get("config_hashes", {})
    try:
        codebook = discover_codebook(private_config_dir)
        settings = discover_settings(private_config_dir)
    except RuntimeError as exc:
        errors.append(str(exc))
        return errors
    if hashes.get("codebook") and hashes["codebook"] != sha256_file(codebook):
        errors.append("codebook hash mismatch with the frozen run manifest")
    if hashes.get("analysis_settings") and hashes["analysis_settings"] != sha256_file(
        settings
    ):
        errors.append("analysis settings hash mismatch with the frozen run manifest")
    frozen_schema = str(hashes.get("schema_version", ""))
    if frozen_schema and frozen_schema != schema_version:
        errors.append(
            f"schema version mismatch: run froze {frozen_schema!r}, worker has {schema_version!r}"
        )
    return errors


def load_or_freeze_manifest(
    *,
    run_id: str,
    project_id: str,
    worker_id: str,
    private_config_dir: Path,
    manifest_store: Any | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Load the frozen manifest from durable storage, or freeze-and-store it.

    ``manifest_store`` is a minimal mapping-like collection with
    ``find_one``/``replace_one`` semantics (e.g. the run manifests collection).
    """
    if manifest_store is None:
        return freeze_manifest(
            run_id=run_id,
            project_id=project_id,
            worker_id=worker_id,
            private_config_dir=private_config_dir,
            repo_root=repo_root,
        )
    existing = manifest_store.find_one({"run_id": run_id, "project_id": project_id})
    if existing is not None:
        existing.pop("_id", None)
        return existing
    manifest = freeze_manifest(
        run_id=run_id,
        project_id=project_id,
        worker_id=worker_id,
        private_config_dir=private_config_dir,
        repo_root=repo_root,
    )
    manifest_store.replace_one(
        {"run_id": run_id, "project_id": project_id}, manifest, upsert=True
    )
    return manifest


def dump_manifest(manifest: dict[str, Any]) -> str:
    """JSON rendering for logs — contains only hashes and public SHAs."""
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, default=str)