from __future__ import annotations

import os
from types import SimpleNamespace

from laclaugpt_data_analysis.llm import routing
from laclaugpt_data_analysis.llm.ollama import (
    OllamaProvider,
    describe_routing,
    publish_llm_host,
    resolve_endpoint,
    resolve_llm_host,
)


def _clear_runtime(monkeypatch) -> None:
    for name in (
        "OLLAMA_HOST",
        "LACLAUGPT_LLM_ENDPOINT",
        "LACLAUGPT_LLM_MODEL",
        "LACLAUGPT_OLLAMA_MODEL",
        "OLLAMA_MODEL",
        "LLM_LOCAL_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_prefixed_endpoint_is_used_when_ollama_host_is_absent(monkeypatch) -> None:
    _clear_runtime(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")
    monkeypatch.setenv("LACLAUGPT_LLM_MODE", "local-ollama")

    assert resolve_llm_host() == "http://127.0.0.1:11500"
    assert resolve_endpoint("gemma4:e4b") == ("local", "gemma4:e4b")
    assert "http://127.0.0.1:11500" in describe_routing("gemma4:e4b")


def test_prefixed_endpoint_outranks_native_ollama_host(monkeypatch) -> None:
    """Issue #77: the project-scoped endpoint must win over an ambient value.

    A shipped example or an unrelated tool can leave ``OLLAMA_HOST`` pointing at
    a different port; the documented AI26 endpoint must still be honoured.
    """
    _clear_runtime(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11600")

    assert resolve_llm_host() == "http://127.0.0.1:11500"
    # An explicit argument still overrides everything.
    assert resolve_llm_host("http://127.0.0.1:11700") == "http://127.0.0.1:11700"


def test_native_ollama_host_is_used_when_prefixed_endpoint_is_absent(monkeypatch) -> None:
    _clear_runtime(monkeypatch)
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11600")

    assert resolve_llm_host() == "http://127.0.0.1:11600"


def test_publish_llm_host_aligns_native_value_with_the_resolved_endpoint(monkeypatch) -> None:
    _clear_runtime(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")

    assert publish_llm_host() == "http://127.0.0.1:11500"
    assert os.environ["OLLAMA_HOST"] == "http://127.0.0.1:11500"

    # A stale native value must not survive next to a different resolved
    # endpoint, or child processes would talk to a different server.
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11600")
    assert publish_llm_host() == "http://127.0.0.1:11500"
    assert os.environ["OLLAMA_HOST"] == "http://127.0.0.1:11500"

    # An explicit argument still never overrides an existing native value.
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11600")
    assert publish_llm_host("http://127.0.0.1:11700") == "http://127.0.0.1:11700"
    assert os.environ["OLLAMA_HOST"] == "http://127.0.0.1:11600"


def test_provider_start_publishes_prefixed_endpoint(monkeypatch) -> None:
    _clear_runtime(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")

    provider = OllamaProvider()

    assert provider._host_override == "http://127.0.0.1:11500"
    assert os.environ["OLLAMA_HOST"] == "http://127.0.0.1:11500"


def test_model_discovery_uses_prefixed_endpoint(monkeypatch) -> None:
    _clear_runtime(monkeypatch)
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
