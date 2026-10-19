"""Regression tests for blank-but-successful model answers (issue #372).

Upstream multimodal #236/#274: Ollama can answer HTTP 200 with ``message.content == ""``.
The old code returned that as a normal answer, so a stage could store an empty
description or checkpoint an empty output as a success. The port makes a blank answer a
bounded retry and then a loud, typed failure, and records how many attempts it took.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from laclaugpt_data_analysis.llm.base import (
    ChatRequest,
    LLMCallProvenance,
    LLMEmptyResponseError,
    LLMResponse,
    empty_response_retries,
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


def _reply(content: str, finish_reason: str = "stop") -> dict:
    return {"message": {"content": content}, "done": True, "done_reason": finish_reason}


def _provider_with(monkeypatch, replies):
    """An OllamaProvider whose client returns `replies` in order and records calls."""
    from laclaugpt_data_analysis.llm import ollama as ollama_module

    calls: list[dict] = []
    queue = iter(replies)

    class FakeClient:
        def chat(self, **kwargs):
            calls.append(kwargs)
            return next(queue)

    monkeypatch.setattr(ollama_module, "resolve_endpoint", lambda model: ("local", model))
    monkeypatch.setattr(ollama_module, "_client", lambda host=None: FakeClient())
    monkeypatch.setattr(ollama_module, "model_digest", lambda model: "")
    return OllamaProvider(), calls


def test_blank_answer_is_retried_and_the_attempt_count_is_recorded(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_EMPTY_RESPONSE_RETRIES", "2")
    provider, calls = _provider_with(
        monkeypatch,
        [_reply(""), _reply("   \n "), _reply("A real description of the item.")],
    )

    response = provider.chat(ChatRequest(model="test-model", system="s", user="u"))

    assert response.content == "A real description of the item."
    assert len(calls) == 3
    assert response.provenance.attempts == 3
    # The request itself is unchanged between attempts: a retry must not quietly
    # rewrite the evidence the model was given.
    assert {call["messages"][1]["content"] for call in calls} == {"u"}


def test_persistently_blank_answer_fails_loudly_instead_of_returning_empty(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_EMPTY_RESPONSE_RETRIES", "1")
    provider, calls = _provider_with(monkeypatch, [_reply(""), _reply("\t")])

    with pytest.raises(LLMEmptyResponseError, match="after 2 attempt"):
        provider.chat(ChatRequest(model="test-model", system="s", user="u"))

    assert len(calls) == 2


def test_zero_retries_fails_on_the_first_blank_answer(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_EMPTY_RESPONSE_RETRIES", "0")
    provider, calls = _provider_with(monkeypatch, [_reply("")])

    with pytest.raises(LLMEmptyResponseError):
        provider.chat(ChatRequest(model="test-model", system="s", user="u"))

    assert len(calls) == 1
    assert empty_response_retries() == 0


def test_retry_count_is_bounded_by_the_environment_contract(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_EMPTY_RESPONSE_RETRIES", "99")
    assert empty_response_retries() == 3
    monkeypatch.setenv("LACLAUGPT_EMPTY_RESPONSE_RETRIES", "not-a-number")
    assert empty_response_retries() == 2


def test_truncated_but_blank_answer_is_not_retried(monkeypatch) -> None:
    """A length stop is a budget problem; retrying the same budget cannot fix it."""
    monkeypatch.setenv("LACLAUGPT_EMPTY_RESPONSE_RETRIES", "2")
    provider, calls = _provider_with(monkeypatch, [_reply("", finish_reason="length")])

    response = provider.chat(ChatRequest(model="test-model", system="s", user="u"))

    assert len(calls) == 1
    assert response.truncated is True
    assert response.content == ""


def test_structured_output_retries_a_blank_answer_without_consuming_validation(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LACLAUGPT_EMPTY_RESPONSE_RETRIES", "2")

    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        def chat(self, request: ChatRequest) -> LLMResponse:
            del request
            self.calls += 1
            if self.calls < 3:
                return LLMResponse(content="  ", provenance=_provenance(), finish_reason="stop")
            return LLMResponse(
                content='{"value": "complete"}', provenance=_provenance(), finish_reason="stop"
            )

    provider = FakeProvider()
    parsed, _response = chat_structured(
        provider,
        _Payload,
        model="test-model",
        system_prompt="system",
        user_prompt="user",
    )

    assert parsed.value == "complete"
    assert provider.calls == 3


def test_structured_output_fails_loudly_when_every_answer_is_blank(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_EMPTY_RESPONSE_RETRIES", "1")

    class BlankProvider:
        def chat(self, request: ChatRequest) -> LLMResponse:
            del request
            return LLMResponse(content="", provenance=_provenance(), finish_reason="stop")

    with pytest.raises(LLMEmptyResponseError, match="empty response after 2 attempt"):
        chat_structured(
            BlankProvider(),
            _Payload,
            model="test-model",
            system_prompt="system",
            user_prompt="user",
        )
