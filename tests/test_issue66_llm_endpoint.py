from __future__ import annotations

import os
from types import SimpleNamespace

from laclaugpt_data_analysis.llm import routing
from laclaugpt_data_analysis.llm.ollama import (
    describe_routing,
    publish_llm_host,
    resolve_endpoint,
    resolve_llm_host,
)


def _clear_hosts(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("LACLAUGPT_LLM_ENDPOINT", raising=False)


def test_prefixed_endpoint_is_used_when_ollama_host_is_absent(monkeypatch) -> None:
    _clear_hosts(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")
    monkeypatch.setenv("LACLAUGPT_LLM_MODE", "local-ollama")

    assert resolve_llm_host() == "http://127.0.0.1:11500"
    assert resolve_endpoint("gemma4:e4b") == ("local", "gemma4:e4b")
    assert "http://127.0.0.1:11500" in describe_routing("gemma4:e4b")


def test_explicit_host_then_ollama_host_take_precedence(monkeypatch) -> None:
    _clear_hosts(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11600")

    assert resolve_llm_host() == "http://127.0.0.1:11600"
    assert resolve_llm_host("http://127.0.0.1:11700") == "http://127.0.0.1:11700"


def test_publish_llm_host_never_overrides_native_setting(monkeypatch) -> None:
    _clear_hosts(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")

    assert publish_llm_host() == "http://127.0.0.1:11500"
    assert os.environ["OLLAMA_HOST"] == "http://127.0.0.1:11500"

    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11600")
    assert publish_llm_host("http://127.0.0.1:11700") == "http://127.0.0.1:11700"
    assert os.environ["OLLAMA_HOST"] == "http://127.0.0.1:11600"


def test_model_discovery_uses_prefixed_endpoint(monkeypatch) -> None:
    _clear_hosts(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500/")
    seen: list[list[str]] = []

    def fake_run(command, **kwargs):
        del kwargs
        seen.append(command)
        return SimpleNamespace(stdout='{"models":[{"name":"gemma4:e4b"}]}')

    monkeypatch.setattr(routing.subprocess, "run", fake_run)
    routing._loaded_models.cache_clear()
    try:
        assert routing._loaded_models() == {"gemma4:e4b"}
    finally:
        routing._loaded_models.cache_clear()

    assert seen[0][-1] == "http://127.0.0.1:11500/api/tags"
