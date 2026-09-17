"""Configuration with one private repository-local runtime root: ``data/``."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .deployment import DeploymentProfile
from .distributed import ProjectNamespace

DATA_SUBDIRS = (
    "logs", "database", "config", "files", "csv", "jsonl", "codebooks", "sources",
    "downloads", "media", "models/ollama", "models/whisper", "cache", "tmp", "exports",
    "artifacts", "runs", "transcripts", "frames",
)


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(f"LACLAUGPT_{name}", default)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw not in (None, "") else default


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = _env(name)
    if raw in (None, ""):
        return default
    return tuple(value.strip() for value in raw.split(",") if value.strip())


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
    # New explicit storage selector. ``data_backend`` remains as a compatibility
    # alias for older configs; storage_backend wins when it is not empty.
    storage_backend: str = "auto"
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
    mongo_vector_index: str = "laclaugpt_record_embedding"
    object_backend: str = "local"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_prefix_root: str = "projects"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    # CSC Allas requires SigV2 uploads and virtual-host compatible addressing.
    # Keep provider-specific behavior configurable for AWS/other S3 backends.
    s3_signature_version: str = "s3"
    s3_addressing_style: str = "auto"
    collection_data_dir: Path | None = None

    rag_enabled: bool = False
    rag_backend: str = "mongodb"
    rag_mode: str = "hybrid"
    rag_top_k: int = 20
    rag_graph_depth: int = 2
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    neo4j_vector_index: str = "laclaugpt_record_embedding"
    embedding_model: str = ""
    embedding_endpoint: str = ""

    periodic_summary_enabled: bool = False
    periodic_summary_interval_hours: int = 24
    periodic_summary_history_context: int = 7
    periodic_summary_use_latest_as_context: bool = True
    periodic_summary_scopes: tuple[str, ...] = (
        "overall", "formation", "signifier", "source", "author"
    )

    luhmann_enabled: bool = False
    luhmann_codebook: Path = Path("codebooks/public/luhmann_social_systems_v1.yaml")
    castells_enabled: bool = False

    @property
    def remote_enabled(self) -> bool:
        return any((self.mongo_url, self.redis_url, self.s3_endpoint_url, self.s3_bucket))

    @property
    def distributed_namespace(self) -> ProjectNamespace:
        return ProjectNamespace(project_id=self.project_id, redis_prefix=self.redis_key_prefix, mongo_database=self.mongo_database, s3_prefix_root=self.s3_prefix_root)

    @property
    def deployment_profile(self) -> DeploymentProfile:
        return DeploymentProfile(machine=self.machine, execution=self.execution, storage=self.storage, llm=self.llm_mode, model=self.llm_model, cloud_allowed=self.cloud_allowed, data_dir=self.data_dir, scratch_dir=self.scratch_dir, collection_data_dir=self.collection_data_dir, ollama_endpoint=self.llm_endpoint, caller=self.caller)

    def data_path(self, *parts: str) -> Path:
        return self.data_dir.joinpath(*parts)

    def ensure_local_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for relative in DATA_SUBDIRS:
            self.data_path(*relative.split("/")).mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
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
        llm_endpoint=_env("LLM_ENDPOINT", "http://127.0.0.1:11434") or "http://127.0.0.1:11434",
        cloud_allowed=_bool_env("CLOUD_ALLOWED", False),
        caller=_env("CALLER", "human-cli") or "human-cli",
        storage_backend=_env("STORAGE_BACKEND", "auto") or "auto",
        data_backend=_env("DATA_BACKEND", "csv") or "csv",
        database_url=_env("DATABASE_URL", "sqlite:///./data/database/analysis.sqlite3") or "sqlite:///./data/database/analysis.sqlite3",
        data_dir=Path(_env("DATA_DIR", "./data") or "./data"),
        artifact_dir=Path(_env("ARTIFACT_DIR", "./data/artifacts") or "./data/artifacts"),
        scratch_dir=Path(scratch) if scratch else None,
        cache_backend=_env("CACHE_BACKEND", "memory") or "memory",
        redis_url=_env("REDIS_URL"),
        redis_key_prefix=_env("REDIS_KEY_PREFIX", "laclaugpt") or "laclaugpt",
        mongo_url=_env("MONGODB_URI") or _env("MONGO_URL"),
        # ``LACLAUGPT_MONGODB_DATABASE`` is the documented contract shared with
        # the Collection module and the AI26 runtime; keep the shorter historical
        # ``LACLAUGPT_MONGO_DATABASE`` working as an alias.
        mongo_database=(
            _env("MONGODB_DATABASE") or _env("MONGO_DATABASE", "laclaugpt") or "laclaugpt"
        ),
        mongo_vector_index=_env("MONGO_VECTOR_INDEX", "laclaugpt_record_embedding") or "laclaugpt_record_embedding",
        object_backend=_env("OBJECT_BACKEND", "local") or "local",
        s3_endpoint_url=_env("S3_ENDPOINT") or _env("S3_ENDPOINT_URL"),
        s3_bucket=_env("S3_BUCKET"),
        s3_region=_env("S3_REGION"),
        s3_prefix_root=_env("S3_PREFIX_ROOT", "projects") or "projects",
        s3_access_key_id=_env("S3_ACCESS_KEY_ID") or _env("S3_ACCESS_KEY"),
        s3_secret_access_key=_env("S3_SECRET_ACCESS_KEY") or _env("S3_SECRET_KEY"),
        s3_signature_version=_env("S3_SIGNATURE_VERSION", "s3") or "s3",
        s3_addressing_style=_env("S3_ADDRESSING_STYLE", "auto") or "auto",
        collection_data_dir=Path(collection_data) if collection_data else None,
        rag_enabled=_bool_env("RAG_ENABLED", False),
        rag_backend=_env("RAG_BACKEND", "mongodb") or "mongodb",
        rag_mode=_env("RAG_MODE", "hybrid") or "hybrid",
        rag_top_k=_int_env("RAG_TOP_K", 20), rag_graph_depth=_int_env("RAG_GRAPH_DEPTH", 2),
        neo4j_uri=_env("NEO4J_URI", "bolt://127.0.0.1:7687") or "bolt://127.0.0.1:7687",
        neo4j_user=_env("NEO4J_USER", "neo4j") or "neo4j",
        neo4j_password=_env("NEO4J_PASSWORD", "") or "",
        neo4j_database=_env("NEO4J_DATABASE", "neo4j") or "neo4j",
        neo4j_vector_index=_env("NEO4J_VECTOR_INDEX", "laclaugpt_record_embedding") or "laclaugpt_record_embedding",
        embedding_model=_env("EMBEDDING_MODEL", "") or "",
        embedding_endpoint=_env("EMBEDDING_ENDPOINT", "") or "",
        periodic_summary_enabled=_bool_env("PERIODIC_SUMMARY_ENABLED", False),
        periodic_summary_interval_hours=_int_env("PERIODIC_SUMMARY_INTERVAL_HOURS", 24),
        periodic_summary_history_context=_int_env("PERIODIC_SUMMARY_HISTORY_CONTEXT", 7),
        periodic_summary_use_latest_as_context=_bool_env("PERIODIC_SUMMARY_USE_LATEST_AS_CONTEXT", True),
        periodic_summary_scopes=_csv_env(
            "PERIODIC_SUMMARY_SCOPES",
            ("overall", "formation", "signifier", "source", "author"),
        ),
        luhmann_enabled=_bool_env("LUHMANN_ENABLED", False),
        luhmann_codebook=Path(_env("LUHMANN_CODEBOOK", "codebooks/public/luhmann_social_systems_v1.yaml") or "codebooks/public/luhmann_social_systems_v1.yaml"),
        castells_enabled=_bool_env("CASTELLS_ENABLED", False),
    )
    errors = settings.deployment_profile.validate()
    if settings.storage_backend.casefold() not in {"auto", "mongodb", "csv", "sqlite"}:
        errors.append(f"unsupported storage backend: {settings.storage_backend}")
    if settings.rag_mode.casefold() not in {"none", "vector", "graph", "hybrid"}:
        errors.append(f"unsupported RAG mode: {settings.rag_mode}")
    if settings.rag_backend.casefold() not in {"mongodb", "neo4j", "none"}:
        errors.append(f"unsupported RAG backend: {settings.rag_backend}")
    if settings.rag_top_k < 1:
        errors.append("RAG top_k must be >= 1")
    if settings.rag_graph_depth < 1 or settings.rag_graph_depth > 5:
        errors.append("RAG graph depth must be between 1 and 5")
    if settings.rag_enabled and settings.rag_mode.casefold() in {"vector", "hybrid"} and not settings.embedding_model:
        errors.append("vector/hybrid RAG requires LACLAUGPT_EMBEDDING_MODEL")
    if settings.storage_backend.casefold() == "mongodb" and not settings.mongo_url:
        errors.append("storage_backend=mongodb requires LACLAUGPT_MONGODB_URI or LACLAUGPT_MONGO_URL")
    if settings.s3_signature_version.casefold() not in {"s3", "s3v4"}:
        errors.append("S3 signature version must be s3 or s3v4")
    if settings.s3_addressing_style.casefold() not in {"auto", "virtual", "path"}:
        errors.append("S3 addressing style must be auto, virtual, or path")
    if settings.periodic_summary_interval_hours < 1:
        errors.append("periodic summary interval hours must be >= 1")
    if settings.periodic_summary_history_context < 0:
        errors.append("periodic summary history context must be >= 0")
    if not settings.periodic_summary_scopes:
        errors.append("periodic summary scopes must not be empty")
    if errors:
        raise ValueError("invalid deployment configuration: " + "; ".join(errors))
    settings.ensure_local_directories()
    return settings
