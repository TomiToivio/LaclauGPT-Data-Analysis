from laclaugpt_data_analysis.config import load_settings


def test_load_settings_reads_s3_client_compatibility_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LACLAUGPT_S3_ACCESS_KEY_ID", "synthetic-access")
    monkeypatch.setenv("LACLAUGPT_S3_SECRET_ACCESS_KEY", "synthetic-secret")
    monkeypatch.setenv("LACLAUGPT_S3_SIGNATURE_VERSION", "s3")
    monkeypatch.setenv("LACLAUGPT_S3_ADDRESSING_STYLE", "auto")

    settings = load_settings()

    assert settings.s3_access_key_id == "synthetic-access"
    assert settings.s3_secret_access_key == "synthetic-secret"
    assert settings.s3_signature_version == "s3"
    assert settings.s3_addressing_style == "auto"


def test_load_settings_accepts_collection_s3_key_aliases(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LACLAUGPT_S3_ACCESS_KEY", "synthetic-access")
    monkeypatch.setenv("LACLAUGPT_S3_SECRET_KEY", "synthetic-secret")
    monkeypatch.delenv("LACLAUGPT_S3_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("LACLAUGPT_S3_SECRET_ACCESS_KEY", raising=False)

    settings = load_settings()

    assert settings.s3_access_key_id == "synthetic-access"
    assert settings.s3_secret_access_key == "synthetic-secret"
