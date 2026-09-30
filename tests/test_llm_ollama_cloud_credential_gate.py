"""Regression coverage for the Ollama cloud credential gate.

CodeQL reported ``py/incomplete-url-substring-sanitization`` on the check that
decides whether to attach ``OLLAMA_API_KEY`` as a bearer token. Testing
``"ollama.com" in host`` on the raw endpoint string matches the domain anywhere
in the URL, so a crafted endpoint such as
``http://evil.example/?next=ollama.com`` would receive the credential.

The gate now parses the endpoint and compares its hostname against the
``ollama.com`` domain. These tests pin both directions: the credential must
reach the real hosted service, and must not reach anything else.
"""
from __future__ import annotations

import pytest

from laclaugpt_data_analysis.llm.ollama import _is_ollama_cloud_host


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://ollama.com",
        "http://ollama.com",
        "ollama.com",
        "ollama.com:443",
        "https://api.ollama.com",
        "https://registry.ollama.com:443",
        "https://OLLAMA.COM",
    ],
)
def test_hosted_cloud_endpoints_are_recognised(endpoint: str) -> None:
    assert _is_ollama_cloud_host(endpoint) is True


@pytest.mark.parametrize(
    "endpoint",
    [
        # The bypass the alert described: the domain appears in the URL but not
        # as the host, so the credential must not be attached.
        "http://evil.example/?next=ollama.com",
        "http://evil-example.net/ollama.com",
        "http://benign-looking-prefix-ollama.com",
        "https://ollama.com.evil.example",
        "notollama.com.evil.example",
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://192.168.1.5:11434",
        "http://ollama.internal:11434",
        "",
    ],
)
def test_non_cloud_endpoints_are_rejected(endpoint: str) -> None:
    assert _is_ollama_cloud_host(endpoint) is False


def test_credential_is_only_attached_for_the_hosted_cloud(monkeypatch) -> None:
    """Drive the real ``_client`` gate, with the ollama dependency stubbed."""

    import sys
    from types import ModuleType

    captured: list[dict] = []

    fake = ModuleType("ollama")

    class _Client:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    fake.Client = _Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ollama", fake)
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key-not-a-real-credential")

    from laclaugpt_data_analysis.llm import ollama as mod

    # Attached for the hosted cloud...
    mod._client("https://ollama.com")
    assert captured[-1].get("headers") == {
        "Authorization": "Bearer test-key-not-a-real-credential"
    }

    # ...and not for any endpoint that merely contains the domain.
    for hostile in (
        "http://evil.example/?next=ollama.com",
        "http://benign-looking-prefix-ollama.com",
        "http://localhost:11434",
    ):
        mod._client(hostile)
        assert "headers" not in captured[-1], f"{hostile!r} received the API key"
