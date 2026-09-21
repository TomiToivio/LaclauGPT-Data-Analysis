from __future__ import annotations

import pytest
from pydantic import BaseModel

from laclaugpt_data_analysis.llm.base import (
    ChatRequest,
    LLMCallProvenance,
    LLMResponse,
    LLMTruncationError,
)
from laclaugpt_data_analysis.llm.ollama import OllamaProvider
from laclaugpt_data_analysis.llm.structured_output import chat_structured


class _Payload(BaseModel):
    value: str


def _provenance() -> LLMCallProvenance:
    return LLMCallProvenance(
        requested_mode="local",
        requested_model="test-model",
        resolved_model="test-model",
        actual_mode="local",
        actual_model="test-model",
    )


def test_ollama_done_reason_length_is_exposed_as_truncation(monkeypatch) -> None:
    from laclaugpt_data_analysis.llm import ollama as ollama_module

    class FakeClient:
        def chat(self, **kwargs):
            del kwargs
            return {
                "message": {"content": '{"value":"cut'},
                "done": True,
                "done_reason": "length",
            }

    monkeypatch.setattr(ollama_module, "resolve_endpoint", lambda model: ("local", model))
    monkeypatch.setattr(ollama_module, "_client", lambda host=None: FakeClient())
    monkeypatch.setattr(ollama_module, "model_digest", lambda model: "")

    response = OllamaProvider().chat(
        ChatRequest(
            model="test-model",
            system="system",
            user="user",
        )
    )

    assert response.finish_reason == "length"
    assert response.truncated is True


def test_structured_truncation_retries_with_larger_output_budget() -> None:
    class FakeProvider:
        def __init__(self):
            self.options: list[dict] = []

        def chat(self, request: ChatRequest) -> LLMResponse:
            self.options.append(dict(request.options))
            if len(self.options) == 1:
                return LLMResponse(
                    content='{"value":"cut',
                    provenance=_provenance(),
                    finish_reason="length",
                    truncated=True,
                )
            return LLMResponse(
                content='{"value":"complete"}',
                provenance=_provenance(),
                finish_reason="stop",
                truncated=False,
            )

    provider = FakeProvider()
    parsed, response = chat_structured(
        provider,
        _Payload,
        model="test-model",
        system_prompt="system",
        user_prompt="user",
    )

    assert parsed.value == "complete"
    assert response.truncated is False
    assert provider.options[0]["num_predict"] == 4096
    assert provider.options[1]["num_predict"] == 8192
    assert provider.options[0]["num_ctx"] >= 16384
    assert provider.options[1]["num_ctx"] >= 16384


def test_repeated_truncation_is_not_reported_as_json_decode_error() -> None:
    class AlwaysTruncated:
        def chat(self, request: ChatRequest) -> LLMResponse:
            del request
            return LLMResponse(
                content='{"value":"cut',
                provenance=_provenance(),
                finish_reason="length",
                truncated=True,
            )

    with pytest.raises(LLMTruncationError, match="output budget"):
        chat_structured(
            AlwaysTruncated(),
            _Payload,
            model="test-model",
            system_prompt="system",
            user_prompt="user",
        )
