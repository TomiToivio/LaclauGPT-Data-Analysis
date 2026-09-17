import os

import pytest

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.distributed_worker import AI26_MODEL, FrozenRunManifest, enforce_local_model
from laclaugpt_data_analysis.llm.ollama import normalize_llm_mode, resolve_endpoint


@pytest.fixture
def manifest() -> FrozenRunManifest:
    return FrozenRunManifest(
        project_id="ai26",
        run_id="run-001",
        schema_version=SCHEMA_VERSION,
        config_sha256="a",
        codebook_sha256="b",
        model=AI26_MODEL,
        public_git_sha="abc",
    )


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    for name in (
        "LLM_MODE",
        "LACLAUGPT_LLM_MODE",
        "LACLAUGPT_OLLAMA_MODE",
        "LLM_ALLOW_CLOUD_FALLBACK",
        "LACLAUGPT_LLM_MODEL",
        "LACLAUGPT_OLLAMA_MODEL",
        "OLLAMA_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_mode_aliases_are_normalized() -> None:
    assert normalize_llm_mode("local") == "local"
    assert normalize_llm_mode("local-ollama") == "local"
    assert normalize_llm_mode("cloud") == "cloud"
    assert normalize_llm_mode("ollama-cloud") == "cloud"
    assert normalize_llm_mode("external") == "external"


def test_prefixed_local_ollama_mode_is_accepted(manifest, monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_LLM_MODE", "local-ollama")

    enforce_local_model(manifest)

    assert os.environ["LLM_MODE"] == "local"
    assert os.environ["LACLAUGPT_LLM_MODE"] == "local-ollama"


def test_unprefixed_local_mode_is_accepted(manifest, monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODE", "local")
    enforce_local_model(manifest)


@pytest.mark.parametrize("name", ["LLM_MODE", "LACLAUGPT_LLM_MODE", "LACLAUGPT_OLLAMA_MODE"])
@pytest.mark.parametrize("value", ["cloud", "ollama-cloud", "external"])
def test_nonlocal_mode_is_rejected_from_every_supported_variable(
    manifest, monkeypatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match="forbids cloud/external"):
        enforce_local_model(manifest)


def test_stale_cloud_mode_cannot_hide_behind_local_prefixed_mode(manifest, monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_LLM_MODE", "local-ollama")
    monkeypatch.setenv("LLM_MODE", "cloud")

    with pytest.raises(ValueError, match="LLM_MODE=cloud"):
        enforce_local_model(manifest)


def test_laclaugpt_llm_model_is_accepted(manifest, monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_LLM_MODE", "local-ollama")
    monkeypatch.setenv("LACLAUGPT_LLM_MODEL", AI26_MODEL)

    enforce_local_model(manifest)

    assert os.environ["LACLAUGPT_LLM_MODEL"] == AI26_MODEL


def test_laclaugpt_llm_model_must_match_manifest(manifest, monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_LLM_MODEL", "other:model")

    with pytest.raises(ValueError, match="configured Ollama model"):
        enforce_local_model(manifest)


def test_provider_accepts_documented_deployment_mode(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_LLM_MODE", "local-ollama")
    monkeypatch.setenv("LACLAUGPT_LLM_MODEL", AI26_MODEL)

    assert resolve_endpoint()[0:2] == ("local", AI26_MODEL)
