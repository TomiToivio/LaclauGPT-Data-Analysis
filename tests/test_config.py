from pathlib import Path

from laclaugpt_data_analysis.config import load_settings


def test_local_defaults_are_zero_config(monkeypatch):
    for name in (
        "PROFILE", "DATA_BACKEND", "DATABASE_URL", "DATA_DIR", "ARTIFACT_DIR",
        "CACHE_BACKEND", "REDIS_URL", "MONGO_URL", "MONGODB_URI", "MONGO_DATABASE",
        "OBJECT_BACKEND", "S3_ENDPOINT", "S3_ENDPOINT_URL", "S3_BUCKET", "S3_REGION",
        "COLLECTION_DATA_DIR",
    ):
        monkeypatch.delenv(f"LACLAUGPT_{name}", raising=False)
    settings = load_settings()
    assert settings.profile == "local"
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


def test_umbrella_distributed_environment_names_are_supported(monkeypatch):
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://example.invalid:27017")
    monkeypatch.setenv("LACLAUGPT_S3_ENDPOINT", "https://object.example.invalid")
    settings = load_settings()
    assert settings.mongo_url == "mongodb://example.invalid:27017"
    assert settings.s3_endpoint_url == "https://object.example.invalid"
