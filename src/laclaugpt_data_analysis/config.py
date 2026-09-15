"""Configuration with privacy-safe local defaults.

Configuration precedence:
1. explicit Settings overrides
2. LACLAUGPT_* environment variables
3. safe local defaults

No credentials, tokens, research data paths or machine-specific secrets belong
in committed configuration files.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(f"LACLAUGPT_{name}", default)


@dataclass(frozen=True)
class Settings:
    profile: str = "local"
    data_backend: str = "csv"
    database_url: str = "sqlite:///./var/laclaugpt.db"
    data_dir: Path = Path("./var/data")
    artifact_dir: Path = Path("./var/artifacts")
    cache_backend: str = "memory"
    redis_url: str | None = None
    mongo_url: str | None = None
    mongo_database: str = "laclaugpt"
    object_backend: str = "local"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None

    @property
    def remote_enabled(self) -> bool:
        return any((self.mongo_url, self.redis_url, self.s3_endpoint_url, self.s3_bucket))


def load_settings() -> Settings:
    """Load environment configuration while keeping local operation zero-config."""
    return Settings(
        profile=_env("PROFILE", "local") or "local",
        data_backend=_env("DATA_BACKEND", "csv") or "csv",
        database_url=_env("DATABASE_URL", "sqlite:///./var/laclaugpt.db") or "sqlite:///./var/laclaugpt.db",
        data_dir=Path(_env("DATA_DIR", "./var/data") or "./var/data"),
        artifact_dir=Path(_env("ARTIFACT_DIR", "./var/artifacts") or "./var/artifacts"),
        cache_backend=_env("CACHE_BACKEND", "memory") or "memory",
        redis_url=_env("REDIS_URL"),
        mongo_url=_env("MONGO_URL"),
        mongo_database=_env("MONGO_DATABASE", "laclaugpt") or "laclaugpt",
        object_backend=_env("OBJECT_BACKEND", "local") or "local",
        s3_endpoint_url=_env("S3_ENDPOINT_URL"),
        s3_bucket=_env("S3_BUCKET"),
        s3_region=_env("S3_REGION"),
    )
