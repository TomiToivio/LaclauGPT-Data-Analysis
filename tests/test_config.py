from pathlib import Path

import pytest

from laclaugpt_data_analysis.config import load_settings


def test_local_defaults_are_zero_config(monkeypatch):
    for name in (
        "PROFILE", "STORAGE", "STORAGE_BACKEND", "DATA_BACKEND", "RECORD_BACKEND",
        "DATABASE_URL", "DATA_DIR", "ARTIFACT_DIR", "CACHE_BACKEND", "REDIS_URL",
        "MONGO_URL", "MONGODB_URI", "MONGO_DATABASE", "MONGODB_DATABASE",
        "MONGO_VECTOR_INDEX", "MONGODB_VECTOR_INDEX", "OBJECT_BACKEND", "S3_ENDPOINT",
        "S3_ENDPOINT_URL", "S3_BUCKET", "S3_REGION", "COLLECTION_DATA_DIR",
    ):
        monkeypatch.delenv(f"LACLAUGPT_{name}", raising=False)
    settings = load_settings()
    assert settings.profile == "local"
    assert settings.storage == "local"
    assert settings.data_backend == "csv"
    assert settings.database_url == "sqlite:///./data/database/analysis.sqlite3"
    assert settings.data_dir == Path("data")
    assert settings.artifact_dir == Path("data/artifacts")
    assert settings.collection_data_dir is None
    assert settings.cache_backend == "memory"
    assert settings.object_backend == "local"
    assert settings.remote_enabled is False


def test_local_collection_path_can_be_shared(monkeypatch):
    monkeypatch.setenv("LACLAUGPT_COLLECTION_DATA_DIR", "../LaclauGPT-Data-Collection/data")
    settings = load_settings()
    assert settings.collection_data_dir == Path("../LaclauGPT-Data-Collection/data")


def test_remote_profile_is_environment_driven(monkeypatch):
    monkeypatch.setenv("LACLAUGPT_DATA_BACKEND", "mongodb")
    monkeypatch.setenv("LACLAUGPT_MONGO_URL", "mongodb://example.invalid:27017")
    monkeypatch.setenv("LACLAUGPT_CACHE_BACKEND", "redis")
    monkeypatch.setenv("LACLAUGPT_REDIS_URL", "redis://example.invalid:6379/0")
    monkeypatch.setenv("LACLAUGPT_OBJECT_BACKEND", "s3")
    monkeypatch.setenv("LACLAUGPT_S3_BUCKET", "example-bucket")
    settings = load_settings()
    assert settings.remote_enabled is True
    assert settings.data_backend == "mongodb"


def test_record_backend_role_selects_distributed_mongodb(monkeypatch):
    for name in ("STORAGE", "STORAGE_BACKEND", "DATA_BACKEND"):
        monkeypatch.delenv(f"LACLAUGPT_{name}", raising=False)
    monkeypatch.setenv("LACLAUGPT_RECORD_BACKEND", "mongodb")
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://example.invalid:27017")
    monkeypatch.setenv("LACLAUGPT_CACHE_BACKEND", "redis")
    monkeypatch.setenv("LACLAUGPT_REDIS_URL", "redis://example.invalid:6379/0")
    monkeypatch.setenv("LACLAUGPT_OBJECT_BACKEND", "s3")
    monkeypatch.setenv("LACLAUGPT_S3_BUCKET", "example-bucket")

    settings = load_settings()

    assert settings.storage == "distributed"
    assert settings.storage_backend == "auto"
    assert settings.data_backend == "mongodb"
    assert settings.cache_backend == "redis"
    assert settings.object_backend == "s3"


def test_explicit_storage_names_override_record_backend_role(monkeypatch):
    monkeypatch.setenv("LACLAUGPT_RECORD_BACKEND", "mongodb")
    monkeypatch.setenv("LACLAUGPT_STORAGE", "local")
    monkeypatch.setenv("LACLAUGPT_DATA_BACKEND", "csv")
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://example.invalid:27017")

    settings = load_settings()

    assert settings.storage == "local"
    assert settings.data_backend == "csv"


def test_unsupported_record_backend_fails_closed(monkeypatch):
    monkeypatch.delenv("LACLAUGPT_STORAGE", raising=False)
    monkeypatch.delenv("LACLAUGPT_DATA_BACKEND", raising=False)
    monkeypatch.setenv("LACLAUGPT_RECORD_BACKEND", "mystery")

    with pytest.raises(ValueError, match="unsupported record backend: mystery"):
        load_settings()


def test_umbrella_distributed_environment_names_are_supported(monkeypatch):
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://example.invalid:27017")
    monkeypatch.setenv("LACLAUGPT_MONGODB_DATABASE", "spectacleScraper")
    monkeypatch.setenv("LACLAUGPT_MONGODB_VECTOR_INDEX", "ai26_embeddings")
    monkeypatch.setenv("LACLAUGPT_S3_ENDPOINT", "https://object.example.invalid")
    settings = load_settings()
    assert settings.mongo_url == "mongodb://example.invalid:27017"
    assert settings.mongo_database == "spectacleScraper"
    assert settings.mongo_vector_index == "ai26_embeddings"
    assert settings.s3_endpoint_url == "https://object.example.invalid"


def test_canonical_mongodb_names_win_over_legacy_aliases(monkeypatch):
    monkeypatch.setenv("LACLAUGPT_MONGODB_DATABASE", "canonical-db")
    monkeypatch.setenv("LACLAUGPT_MONGO_DATABASE", "legacy-db")
    monkeypatch.setenv("LACLAUGPT_MONGODB_VECTOR_INDEX", "canonical-index")
    monkeypatch.setenv("LACLAUGPT_MONGO_VECTOR_INDEX", "legacy-index")
    settings = load_settings()
    assert settings.mongo_database == "canonical-db"
    assert settings.mongo_vector_index == "canonical-index"


def test_legacy_mongo_names_remain_supported(monkeypatch):
    monkeypatch.delenv("LACLAUGPT_MONGODB_DATABASE", raising=False)
    monkeypatch.delenv("LACLAUGPT_MONGODB_VECTOR_INDEX", raising=False)
    monkeypatch.setenv("LACLAUGPT_MONGO_DATABASE", "legacy-db")
    monkeypatch.setenv("LACLAUGPT_MONGO_VECTOR_INDEX", "legacy-index")
    settings = load_settings()
    assert settings.mongo_database == "legacy-db"
    assert settings.mongo_vector_index == "legacy-index"
