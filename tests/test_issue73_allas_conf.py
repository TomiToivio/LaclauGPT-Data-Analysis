from __future__ import annotations

from pathlib import Path

from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.preflight import _check_object_store
from laclaugpt_data_analysis.storage import S3ArtifactStore


def _write_allas_conf_files(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config"
    credentials = tmp_path / "credentials"
    config.write_text("[default]\nendpoint_url = https://a3s.fi\n", encoding="utf-8")
    credentials.write_text(
        "[default]\n"
        "aws_access_key_id = TESTACCESSKEY\n"
        "aws_secret_access_key = TESTSECRETKEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(credentials))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def test_s3_artifact_store_uses_allas_conf_without_laclaugpt_credentials(
    tmp_path, monkeypatch
):
    _write_allas_conf_files(tmp_path, monkeypatch)

    store = S3ArtifactStore(
        "test-bucket",
        endpoint_url=None,
        region="",
        access_key_id=None,
        secret_access_key=None,
        signature_version="s3",
        addressing_style="virtual",
    )

    assert store.client.meta.endpoint_url == "https://a3s.fi"
    url = store.client.generate_presigned_url(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "object.txt"},
        ExpiresIn=60,
    )
    assert url.startswith("https://test-bucket.a3s.fi/object.txt?")
    assert "AWSAccessKeyId=TESTACCESSKEY" in url
    assert "Signature=" in url
    assert "X-Amz-Algorithm=" not in url


class FakeStore:
    created: list["FakeStore"] = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.puts: list[tuple[str, bytes, str]] = []
        self.deletes: list[str] = []
        self.__class__.created.append(self)

    def put_bytes(self, key: str, value: bytes, *, content_type: str):
        self.puts.append((key, value, content_type))
        return f"s3://test/{key}"

    def delete(self, key: str) -> None:
        self.deletes.append(key)


def test_preflight_checks_write_using_same_s3_adapter(monkeypatch):
    FakeStore.created.clear()
    monkeypatch.setattr("laclaugpt_data_analysis.preflight.S3ArtifactStore", FakeStore)
    settings = Settings(
        project_id="ai26",
        object_backend="s3",
        s3_bucket="shared-ai26-bucket",
        s3_endpoint_url=None,
        s3_region=None,
        s3_signature_version="s3",
        s3_addressing_style="virtual",
    )

    report = _check_object_store(settings)

    assert report["reachable"] is True
    assert report["writeable"] is True
    assert report["cleanup"] is True
    assert report["endpoint"] == "shared-aws-config"
    store = FakeStore.created[-1]
    assert store.kwargs["access_key_id"] is None
    assert store.kwargs["secret_access_key"] is None
    assert store.kwargs["signature_version"] == "s3"
    assert store.kwargs["addressing_style"] == "virtual"
    assert len(store.puts) == 1
    key, body, content_type = store.puts[0]
    assert key.startswith(".preflight/")
    assert body == b"laclaugpt-preflight\n"
    assert content_type == "text/plain"
    assert store.deletes == [key]
