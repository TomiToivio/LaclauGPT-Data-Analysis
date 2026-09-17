from types import SimpleNamespace

from laclaugpt_data_analysis.llm import ollama, routing


def _clear_endpoint_env(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("LACLAUGPT_LLM_ENDPOINT", raising=False)


def test_prefixed_endpoint_alias_is_honoured(monkeypatch):
    _clear_endpoint_env(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")

    assert ollama.resolve_llm_host() == "http://127.0.0.1:11500"


def test_native_ollama_host_wins_over_prefixed_alias(monkeypatch):
    _clear_endpoint_env(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11600")

    assert ollama.resolve_llm_host() == "http://127.0.0.1:11600"


def test_explicit_host_wins_over_environment(monkeypatch):
    _clear_endpoint_env(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11600")

    assert ollama.resolve_llm_host("http://127.0.0.1:11700") == "http://127.0.0.1:11700"


def test_resolve_endpoint_sees_prefixed_external_endpoint(monkeypatch):
    _clear_endpoint_env(monkeypatch)
    monkeypatch.delenv("LLM_MODE", raising=False)
    monkeypatch.delenv("LACLAUGPT_LLM_MODE", raising=False)
    monkeypatch.delenv("LACLAUGPT_OLLAMA_MODE", raising=False)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://ollama.internal:11434")

    mode, _ = ollama.resolve_endpoint("gemma4:e4b")

    assert mode == "external"


def test_model_discovery_uses_prefixed_endpoint_alias(monkeypatch):
    _clear_endpoint_env(monkeypatch)
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")
    routing._loaded_models.cache_clear()
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return SimpleNamespace(stdout='{"models": [{"name": "gemma4:e4b"}]}')

    monkeypatch.setattr(routing.subprocess, "run", fake_run)

    assert routing._loaded_models() == {"gemma4:e4b"}
    assert seen["args"][-1] == "http://127.0.0.1:11500/api/tags"
    routing._loaded_models.cache_clear()
