import sys
from types import ModuleType, SimpleNamespace

from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.storage import (
    CsvStore,
    LocalArtifactStore,
    MemoryCache,
    S3ArtifactStore,
    SqliteStore,
    artifact_store,
)


def test_csv_roundtrip(tmp_path):
    store = CsvStore(tmp_path / "rows.csv")
    rows = [{"id": "1", "text": "hello"}, {"id": "2", "text": "world"}]
    store.write(rows)
    assert store.read() == rows


def test_sqlite_roundtrip(tmp_path):
    store = SqliteStore(tmp_path / "rows.sqlite3")
    rows = [{"id": 1, "label": "accel"}, {"id": 2, "label": "critical"}]
    store.write(rows)
    assert store.read() == rows


def test_local_artifact_store(tmp_path):
    store = LocalArtifactStore(tmp_path)
    store.put_text("reports/example.txt", "analysis")
    assert store.get_text("reports/example.txt") == "analysis"
    assert store.exists("reports/example.txt")
    store.delete("reports/example.txt")
    assert not store.exists("reports/example.txt")


def _install_fake_boto(monkeypatch):
    calls = []

    class FakeConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def client(service, **kwargs):
        calls.append((service, kwargs))
        return SimpleNamespace()

    boto3 = ModuleType("boto3")
    boto3.client = client
    botocore = ModuleType("botocore")
    botocore_config = ModuleType("botocore.config")
    botocore_config.Config = FakeConfig
    botocore.config = botocore_config
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    monkeypatch.setitem(sys.modules, "botocore", botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", botocore_config)
    return calls


def test_s3_artifact_store_constructs_allas_compatible_client(monkeypatch):
    calls = _install_fake_boto(monkeypatch)

    S3ArtifactStore(
        "LaclauGPT-AI26",
        endpoint_url="https://a3s.fi",
        region="regionOne",
        access_key_id="synthetic-access",
        secret_access_key="synthetic-secret",
        signature_version="s3",
        addressing_style="auto",
    )

    service, kwargs = calls[0]
    assert service == "s3"
    assert kwargs["endpoint_url"] == "https://a3s.fi"
    assert kwargs["region_name"] == "regionOne"
    assert kwargs["aws_access_key_id"] == "synthetic-access"
    assert kwargs["aws_secret_access_key"] == "synthetic-secret"
    assert kwargs["config"].kwargs == {
        "signature_version": "s3",
        "s3": {"addressing_style": "auto"},
    }


def test_artifact_store_forwards_s3_client_settings(monkeypatch):
    calls = _install_fake_boto(monkeypatch)
    settings = Settings(
        project_id="ai26",
        object_backend="s3",
        s3_endpoint_url="https://a3s.fi",
        s3_bucket="LaclauGPT-AI26",
        s3_region="regionOne",
        s3_access_key_id="synthetic-access",
        s3_secret_access_key="synthetic-secret",
        s3_signature_version="s3",
        s3_addressing_style="auto",
    )

    store = artifact_store(settings)

    _, kwargs = calls[0]
    assert store.prefix == "projects/ai26/analysis"
    assert kwargs["aws_access_key_id"] == "synthetic-access"
    assert kwargs["aws_secret_access_key"] == "synthetic-secret"
    assert kwargs["config"].kwargs["signature_version"] == "s3"
    assert kwargs["config"].kwargs["s3"] == {"addressing_style": "auto"}


def test_memory_cache():
    cache = MemoryCache()
    assert cache.get("missing") is None
    cache.set("key", "value")
    assert cache.get("key") == "value"
