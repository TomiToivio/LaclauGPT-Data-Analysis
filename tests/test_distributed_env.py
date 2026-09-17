"""Tests for the distributed AI26 environment contract (issue #15 family)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from laclaugpt_data_analysis.distributed_env import (
    MONGODB_URI_ENV,
    PRIVATE_CONFIG_DIR_ENV,
    REDIS_URL_ENV,
    RUN_ID_ENV,
    S3_ACCESS_KEY_ENV,
    S3_BUCKET_ENV,
    S3_ENDPOINT_ENV,
    S3_SECRET_KEY_ENV,
    TEST_MODEL,
    enforce_local_model_policy,
    resolve_distributed_env,
)

CONTRACT = {
    RUN_ID_ENV: "ai26-dist-test-001",
    MONGODB_URI_ENV: "mongodb://localhost:27017",
    REDIS_URL_ENV: "redis://localhost:6379/0",
    S3_ENDPOINT_ENV: "https://object-storage.example.invalid",
    S3_BUCKET_ENV: "bucket-name",
    S3_ACCESS_KEY_ENV: "test-access",
    S3_SECRET_KEY_ENV: "test-secret",
}


@pytest.fixture()
def private_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "private-ai26"
    (config_dir / "codebooks").mkdir(parents=True)
    (config_dir / "codebooks" / "ai26-codebook.yaml").write_text(
        "entries: []\n", encoding="utf-8"
    )
    (config_dir / "projects").mkdir()
    (config_dir / "projects" / "ai26.yaml").write_text("project: ai26\n", encoding="utf-8")
    return config_dir


def test_missing_contract_fails_closed_with_all_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (*CONTRACT, PRIVATE_CONFIG_DIR_ENV):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        resolve_distributed_env()
    message = str(excinfo.value)
    for key in sorted((*CONTRACT, PRIVATE_CONFIG_DIR_ENV)):
        assert key in message


def test_full_contract_resolves(monkeypatch: pytest.MonkeyPatch, private_config: Path) -> None:
    env_values = {**CONTRACT, PRIVATE_CONFIG_DIR_ENV: str(private_config)}
    for key, value in env_values.items():
        monkeypatch.setenv(key, value)
    env = resolve_distributed_env()
    assert env.run_id == "ai26-dist-test-001"
    assert env.project_id == "ai26"
    assert env.private_config_dir == private_config
    assert env.ollama_host == "http://127.0.0.1:11434"
    # secrets never appear in repr
    assert "test-secret" not in repr(env)
    assert "test-access" not in repr(env)


def test_legacy_mongo_alias_accepted(monkeypatch: pytest.MonkeyPatch, private_config: Path) -> None:
    for key, value in {
        **CONTRACT,
        PRIVATE_CONFIG_DIR_ENV: str(private_config),
        MONGODB_URI_ENV: "",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LACLAUGPT_MONGO_URL", "mongodb://alias:27017")
    env = resolve_distributed_env()
    assert env.mongodb_uri == "mongodb://alias:27017"


def test_private_config_dir_missing_fails_closed(
    monkeypatch: pytest.MonkeyPatch, private_config: Path
) -> None:
    for key, value in {
        **CONTRACT,
        PRIVATE_CONFIG_DIR_ENV: str(private_config / "does-not-exist"),
    }.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match="readable private config"):
        resolve_distributed_env()


def test_require_private_config_false_allows_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for key, value in {**CONTRACT, PRIVATE_CONFIG_DIR_ENV: str(tmp_path)}.items():
        monkeypatch.setenv(key, value)
    env = resolve_distributed_env(require_private_config=False)
    assert env.private_config_dir == tmp_path


def test_cloud_model_policy_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ALLOW_CLOUD_FALLBACK", "1")
    with pytest.raises(RuntimeError, match="cloud fallback is forbidden"):
        enforce_local_model_policy(TEST_MODEL, allow_cloud_fallback=True)
    with pytest.raises(RuntimeError, match="forbidden"):
        enforce_local_model_policy("gemma4:31b-cloud")


def test_local_model_allowed() -> None:
    enforce_local_model_policy(TEST_MODEL)
    enforce_local_model_policy("gemma4:e4b")