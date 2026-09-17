"""Distributed-run environment contract for the AI26 three-machine test.

One consistent variable contract across Collection, Analysis and Visualization
(issue #15 family). Modules keep their documented legacy aliases; this module
resolves the shared environment for distributed AI26 runs and fails closed when
required private configuration is unavailable.
"""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path

RUN_ID_ENV = "LACLAUGPT_RUN_ID"
MONGODB_URI_ENV = "LACLAUGPT_MONGODB_URI"
REDIS_URL_ENV = "LACLAUGPT_REDIS_URL"
S3_ENDPOINT_ENV = "LACLAUGPT_S3_ENDPOINT"
S3_BUCKET_ENV = "LACLAUGPT_S3_BUCKET"
S3_ACCESS_KEY_ENV = "LACLAUGPT_S3_ACCESS_KEY"
S3_SECRET_KEY_ENV = "LACLAUGPT_S3_SECRET_KEY"
PRIVATE_CONFIG_DIR_ENV = "LACLAUGPT_PRIVATE_CONFIG_DIR"
OLLAMA_HOST_ENV = "OLLAMA_HOST"
PROJECT_ID_ENV = "LACLAUGPT_PROJECT_ID"
WORKER_ID_ENV = "LACLAUGPT_WORKER_ID"
MACHINE_ENV = "LACLAUGPT_MACHINE"
EXECUTION_ENV = "LACLAUGPT_EXECUTION"

TEST_MODEL = "gemma4:12b"

# Documented legacy aliases accepted per module (first match wins).
MONGODB_URI_ALIASES = (MONGODB_URI_ENV, "LACLAUGPT_MONGO_URL", "LACLAUGPT_VIS_MONGODB_URI")
REDIS_URL_ALIASES = (REDIS_URL_ENV, "LACLAUGPT_VIS_REDIS_URL")
S3_ENDPOINT_ALIASES = (S3_ENDPOINT_ENV, "LACLAUGPT_S3_ENDPOINT_URL")
S3_BUCKET_ALIASES = (S3_BUCKET_ENV,)
S3_ACCESS_KEY_ALIASES = (S3_ACCESS_KEY_ENV, "LACLAUGPT_S3_ACCESS_KEY_ID")
S3_SECRET_KEY_ALIASES = (S3_SECRET_KEY_ENV, "LACLAUGPT_S3_SECRET_ACCESS_KEY")


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


@dataclass(frozen=True)
class DistributedRunEnv:
    """Resolved distributed environment; secrets are repr-masked."""

    run_id: str
    project_id: str
    mongodb_uri: str
    redis_url: str
    s3_endpoint: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str
    private_config_dir: Path
    ollama_host: str
    worker_id: str
    machine: str
    execution: str

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"DistributedRunEnv(run_id={self.run_id!r}, project_id={self.project_id!r}, "
            f"mongodb_uri=<set>, redis_url=<set>, s3_endpoint={self.s3_endpoint!r}, "
            f"s3_bucket={self.s3_bucket!r}, private_config_dir={str(self.private_config_dir)!r}, "
            f"ollama_host={self.ollama_host!r}, worker_id={self.worker_id!r}, "
            f"machine={self.machine!r}, execution={self.execution!r})"
        )


def _default_worker_id() -> str:
    """Stable-ish worker identity without exposing full hostnames in logs."""
    role = os.environ.get(MACHINE_ENV) or "worker"
    return f"{role}-{socket.gethostname()[:24]}"


def resolve_distributed_env(
    *,
    default_project_id: str = "ai26",
    require_private_config: bool = True,
) -> DistributedRunEnv:
    """Resolve the shared environment contract; fail closed on missing pieces.

    Raises RuntimeError listing every missing variable at once, and refuses a
    private-config directory that is not a readable directory. No secret value
    is ever included in error messages, only the variable names.
    """
    missing: list[str] = []
    if not os.environ.get(RUN_ID_ENV):
        missing.append(RUN_ID_ENV)
    if not _first_env(MONGODB_URI_ALIASES):
        missing.append(MONGODB_URI_ENV)
    if not _first_env(REDIS_URL_ALIASES):
        missing.append(REDIS_URL_ENV)
    if not _first_env(S3_ENDPOINT_ALIASES):
        missing.append(S3_ENDPOINT_ENV)
    if not _first_env(S3_BUCKET_ALIASES):
        missing.append(S3_BUCKET_ENV)
    if not _first_env(S3_ACCESS_KEY_ALIASES):
        missing.append(S3_ACCESS_KEY_ENV)
    if not _first_env(S3_SECRET_KEY_ALIASES):
        missing.append(S3_SECRET_KEY_ENV)
    private_dir = os.environ.get(PRIVATE_CONFIG_DIR_ENV)
    if not private_dir:
        missing.append(PRIVATE_CONFIG_DIR_ENV)

    if missing:
        raise RuntimeError(
            "AI26 distributed run requires missing environment variables: "
            + ", ".join(sorted(missing))
            + "; export the shared contract before starting workers"
        )

    path = Path(private_dir or ".")
    if require_private_config and not (path.is_dir() and os.access(path, os.R_OK)):
        raise RuntimeError(
            f"{PRIVATE_CONFIG_DIR_ENV} must point to a readable private config directory"
        )

    return DistributedRunEnv(
        run_id=os.environ[RUN_ID_ENV],
        project_id=os.environ.get(PROJECT_ID_ENV) or default_project_id,
        mongodb_uri=_first_env(MONGODB_URI_ALIASES) or "",
        redis_url=_first_env(REDIS_URL_ALIASES) or "",
        s3_endpoint=_first_env(S3_ENDPOINT_ALIASES) or "",
        s3_bucket=_first_env(S3_BUCKET_ALIASES) or "",
        s3_access_key=_first_env(S3_ACCESS_KEY_ALIASES) or "",
        s3_secret_key=_first_env(S3_SECRET_KEY_ALIASES) or "",
        private_config_dir=path,
        ollama_host=os.environ.get(OLLAMA_HOST_ENV, "http://127.0.0.1:11434"),
        worker_id=os.environ.get(WORKER_ID_ENV) or _default_worker_id(),
        machine=os.environ.get(MACHINE_ENV) or "custom",
        execution=os.environ.get(EXECUTION_ENV) or "cli",
    )


def enforce_local_model_policy(model: str, *, allow_cloud_fallback: bool = False) -> None:
    """Reject cloud models/fallback for the distributed AI26 test (fail closed)."""
    if allow_cloud_fallback:
        raise RuntimeError("cloud fallback is forbidden in the AI26 distributed test")
    from .deployment import CLOUD_MODELS

    if model in CLOUD_MODELS:
        raise RuntimeError(f"cloud model {model!r} is forbidden; use local {TEST_MODEL!r}")
