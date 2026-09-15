"""Configuration with one private repository-local runtime root: ``data/``."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class Settings:
    profile: str = "local"
    data_backend: str = "csv"
    database_url: str = "sqlite:///./data/database/analysis.sqlite3"
    data_dir: Path = Path("./data")
    artifact_dir: Path = Path("./data/artifacts")
    cache_backend: str = "memory"
    redis_url: str | None = None
    mongo_url: str | None = None
    mongo_database: str = "laclaugpt"
    object_backend: str = "local"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    collection_data_dir: Path | None = None

    @property
    def remote_enabled(self) -> bool:
        return any((self.mongo_url, self.redis_url, self.s3_endpoint_url, self.s3_bucket))

    def data_path(self, *parts: str) -> Path:
        return self.data_dir.joinpath(*parts)

    def ensure_local_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for relative in DATA_SUBDIRS:
            self.data_path(*relative.split("/")).mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    """Load settings and initialize the ignored local runtime directory tree."""
    collection_data = _env("COLLECTION_DATA_DIR")
    settings = Settings(
        profile=_env("PROFILE", "local") or "local",
        data_backend=_env("DATA_BACKEND", "csv") or "csv",
        database_url=_env("DATABASE_URL", "sqlite:///./data/database/analysis.sqlite3")
        or "sqlite:///./data/database/analysis.sqlite3",
        data_dir=Path(_env("DATA_DIR", "./data") or "./data"),
        artifact_dir=Path(_env("ARTIFACT_DIR", "./data/artifacts") or "./data/artifacts"),
        cache_backend=_env("CACHE_BACKEND", "memory") or "memory",
        redis_url=_env("REDIS_URL"),
        mongo_url=_env("MONGO_URL"),
        mongo_database=_env("MONGO_DATABASE", "laclaugpt") or "laclaugpt",
        object_backend=_env("OBJECT_BACKEND", "local") or "local",
        s3_endpoint_url=_env("S3_ENDPOINT_URL"),
        s3_bucket=_env("S3_BUCKET"),
        s3_region=_env("S3_REGION"),
        collection_data_dir=Path(collection_data) if collection_data else None,
    )
    settings.ensure_local_directories()
    return settings
