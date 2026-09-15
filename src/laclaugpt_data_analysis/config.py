"""Configuration with one private repository-local runtime root: ``data/``."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .deployment import DeploymentProfile
from .distributed import ProjectNamespace

DATA_SUBDIRS = (
    "logs",
    "database",
    "config",
    "files",
    "csv",
    "jsonl",
    "codebooks",
    "sources",
    "downloads",
    "media",
    "models/ollama",
    "models/whisper",
    "cache",
    "tmp",
    "exports",
    "artifacts",
    "runs",
    "transcripts",
    "frames",
)


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(f"LACLAUGPT_{name}", default)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    project_id: str = "default"
    profile: str = "local"
    machine: str = "laptop"
    execution: str = "cli"
    storage: str = "local"
    llm_mode: str = "local-ollama"
    llm_model: str = "gemma4:e4b"
    llm_endpoint: str = "http://127.0.0.1:11434"
    cloud_allowed: bool = False
    caller: str = "human-cli"
    data_backend: str = "csv"
    database_url: str = "sqlite:///./data/database/analysis.sqlite3"
    data_dir: Path = Path("./data")
    artifact_dir: Path = Path("./data/artifacts")
    scratch_dir: Path | None = None
    cache_backend: str = "memory"
    redis_url: str | None = None
    redis_key_prefix: str = "laclaugpt"
    mongo_url: str | None = None
    mongo_database: str = "laclaugpt"
    object_backend: str = "local"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_prefix_root: str = "projects"
    collection_data_dir: Path | None = None

    @property
    def remote_enabled(self) -> bool:
        return any((self.mongo_url, self.redis_url, self.s3_endpoint_url, self.s3_bucket))

    @property
    def distributed_namespace(self) -> ProjectNamespace:
        return ProjectNamespace(
            project_id=self.project_id,
            redis_prefix=self.redis_key_prefix,
            mongo_database=self.mongo_database,
            s3_prefix_root=self.s3_prefix_root,
        )

    @property
    def deployment_profile(self) -> DeploymentProfile:
        return DeploymentProfile(
            machine=self.machine,
            execution=self.execution,
            storage=self.storage,
            llm=self.llm_mode,
            model=self.llm_model,
            cloud_allowed=self.cloud_allowed,
            data_dir=self.data_dir,
            scratch_dir=self.scratch_dir,
            collection_data_dir=self.collection_data_dir,
            ollama_endpoint=self.llm_endpoint,
            caller=self.caller,
        )

    def data_path(self, *parts: str) -> Path:
        return self.data_dir.joinpath(*parts)

    def ensure_local_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for relative in DATA_SUBDIRS:
            self.data_path(*relative.split("/")).mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    """Load settings and initialize the ignored local runtime directory tree."""
    collection_data = _env("COLLECTION_DATA_DIR")
    scratch = _env("SCRATCH_DIR")
    settings = Settings(
        project_id=_env("PROJECT_ID", "default") or "default",
        profile=_env("PROFILE", "local") or "local",
        machine=_env("MACHINE", "laptop") or "laptop",
        execution=_env("EXECUTION", "cli") or "cli",
        storage=_env("STORAGE", "local") or "local",
        llm_mode=_env("LLM_MODE", "local-ollama") or "local-ollama",
        llm_model=_env("LLM_MODEL", "gemma4:e4b") or "gemma4:e4b",
        llm_endpoint=_env("LLM_ENDPOINT", "http://127.0.0.1:11434")
        or "http://127.0.0.1:11434",
        cloud_allowed=_bool_env("CLOUD_ALLOWED", False),
        caller=_env("CALLER", "human-cli") or "human-cli",
        data_backend=_env("DATA_BACKEND", "csv") or "csv",
        database_url=_env("DATABASE_URL", "sqlite:///./data/database/analysis.sqlite3")
        or "sqlite:///./data/database/analysis.sqlite3",
        data_dir=Path(_env("DATA_DIR", "./data") or "./data"),
        artifact_dir=Path(_env("ARTIFACT_DIR", "./data/artifacts") or "./data/artifacts"),
        scratch_dir=Path(scratch) if scratch else None,
        cache_backend=_env("CACHE_BACKEND", "memory") or "memory",
        redis_url=_env("REDIS_URL"),
        redis_key_prefix=_env("REDIS_KEY_PREFIX", "laclaugpt") or "laclaugpt",
        mongo_url=_env("MONGO_URL"),
        mongo_database=_env("MONGO_DATABASE", "laclaugpt") or "laclaugpt",
        object_backend=_env("OBJECT_BACKEND", "local") or "local",
        s3_endpoint_url=_env("S3_ENDPOINT_URL"),
        s3_bucket=_env("S3_BUCKET"),
        s3_region=_env("S3_REGION"),
        s3_prefix_root=_env("S3_PREFIX_ROOT", "projects") or "projects",
        collection_data_dir=Path(collection_data) if collection_data else None,
    )
    settings.distributed_namespace
    errors = settings.deployment_profile.validate()
    if errors:
        raise ValueError("invalid deployment configuration: " + "; ".join(errors))
    settings.ensure_local_directories()
    return settings
