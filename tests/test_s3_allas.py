from __future__ import annotations

from pathlib import Path

import pytest

from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.preflight import _check_object_store
from laclaugpt_data_analysis.s3_client import (
    S3ClientSpec,
    build_s3_client,
    normalize_signature_version,
)
from laclaugpt_data_analysis.storage import artifact_store


def _allas_aws_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)


def test_allas_conf_style_aws_files_need_no_laclaugpt_credentials(tmp_path, monkeypatch):
    _allas_aws_files(tmp_path, monkeypatch)

    client, spec = build_s3_client()

    assert spec.provider == "allas"
    assert spec.endpoint_url == "https://a3s.fi"
    assert spec.region is None
    assert spec.addressing_style == "virtual"
    assert spec.signature_version == "s3"
    assert client.meta.endpoint_url == "https://a3s.fi"

    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "object.txt"},
        ExpiresIn=60,
    )
    assert url.startswith("https://test-bucket.a3s.fi/object.txt?")
    assert "AWSAccessKeyId=TESTACCESSKEY" in url
    assert "Signature=" in url
    assert "X-Amz-Algorithm=" not in url


def test_explicit_s3v2_alias_maps_to_botocore_s3():
    assert normalize_signature_version("s3v2") == "s3"
    assert normalize_signature_version("v2") == "s3"
    assert normalize_signature_version("s3") == "s3"
    assert normalize_signature_version("s3v4") == "s3v4"


def test_empty_region_is_normalized_for_allas(tmp_path, monkeypatch):
    _allas_aws_files(tmp_path, monkeypatch)
    _, spec = build_s3_client(region="   ")
    assert spec.region is None


def test_artifact_store_uses_allas_conf_without_endpoint_env(tmp_path, monkeypatch):
    _allas_aws_files(tmp_path, monkeypatch)
    settings = Settings(
        project_id="ai26",
        object_backend="s3",
        s3_bucket="shared-ai26-bucket",
        s3_endpoint_url=None,
        s3_region="",
    )

    store = artifact_store(settings)

    assert store.client_spec.provider == "allas"
    assert store.client_spec.endpoint_url == "https://a3s.fi"
    assert store.client_spec.addressing_style == "virtual"
    assert store.client_spec.signature_version == "s3"


def test_invalid_transport_settings_fail_before_network(tmp_path, monkeypatch):
    _allas_aws_files(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="addressing style"):
        build_s3_client(addressing_style="hostname-ish")
    with pytest.raises(ValueError, match="signature version"):
        build_s3_client(signature_version="s3v2-typo")


class _FakeWritableS3:
    def __init__(self):
        self.puts: list[dict[str, object]] = []
        self.deletes: list[dict[str, object]] = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)

    def delete_object(self, **kwargs):
        self.deletes.append(kwargs)


def test_preflight_verifies_project_scoped_write_and_cleanup(monkeypatch):
    client = _FakeWritableS3()
    spec = S3ClientSpec(
        endpoint_url="https://a3s.fi",
        region=None,
        addressing_style="virtual",
        signature_version="s3",
        provider="allas",
    )
    monkeypatch.setattr(
        "laclaugpt_data_analysis.preflight.build_s3_client",
        lambda **kwargs: (client, spec),
    )
    settings = Settings(
        project_id="ai26",
        object_backend="s3",
        s3_bucket="shared-ai26-bucket",
    )

    report = _check_object_store(settings)

    assert report["reachable"] is True
    assert report["writeable"] is True
    assert report["cleanup"] is True
    assert report["provider"] == "allas"
    assert len(client.puts) == 1
    assert len(client.deletes) == 1
    key = str(client.puts[0]["Key"])
    assert key.startswith("projects/ai26/analysis/.preflight/")
    assert client.deletes[0]["Key"] == key
