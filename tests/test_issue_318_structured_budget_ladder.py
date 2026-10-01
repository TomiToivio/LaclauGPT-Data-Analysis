"""Regression coverage for issue #318: bounded 16K recovery on truncation."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from laclaugpt_data_analysis.llm.base import (
    ChatRequest,
    LLMCallProvenance,
    LLMResponse,
    LLMTruncationError,
)
from laclaugpt_data_analysis.llm.structured_output import chat_structured


class Payload(BaseModel):
    value: str


def _provenance() -> LLMCallProvenance:
    return LLMCallProvenance(
        requested_mode="local",
        requested_model="synthetic",
        resolved_model="synthetic",
        actual_mode="local",
        actual_model="synthetic",
    )


def _truncated() -> LLMResponse:
    return LLMResponse(
        content='{"value":"unfinished',
        provenance=_provenance(),
        finish_reason="length",
        truncated=True,
    )


def test_recovers_on_third_bounded_attempt_with_larger_context() -> None:
    class Provider:
        def __init__(self) -> None:
            self.options: list[dict] = []

        def chat(self, request: ChatRequest) -> LLMResponse:
            self.options.append(dict(request.options))
            if len(self.options) < 3:
                return _truncated()
            return LLMResponse(
                content='{"value":"complete"}',
                provenance=_provenance(),
                finish_reason="stop",
                truncated=False,
            )

    provider = Provider()
    parsed, _ = chat_structured(
        provider,
        Payload,
        model="synthetic",
        system_prompt="system",
        user_prompt="input",
    )

    assert parsed.value == "complete"
    assert [row["num_predict"] for row in provider.options] == [4096, 8192, 16384]
    assert provider.options[0]["num_ctx"] >= 16384
    assert provider.options[1]["num_ctx"] >= 16384
    assert provider.options[2]["num_ctx"] >= 32768


def test_runtime_ceiling_override_allows_controlled_8192_measurement(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_MAX_STRUCTURED_NUM_PREDICT", "8192")

    class Provider:
        def __init__(self) -> None:
            self.budgets: list[int] = []

        def chat(self, request: ChatRequest) -> LLMResponse:
            self.budgets.append(int(request.options["num_predict"]))
            return _truncated()

    provider = Provider()
    with pytest.raises(LLMTruncationError) as caught:
        chat_structured(
            provider,
            Payload,
            model="synthetic",
            system_prompt="system",
            user_prompt="input",
        )

    assert provider.budgets == [4096, 8192]
    assert caught.value.output_budget_tokens == 8192
    assert caught.value.required_output_tokens_lower_bound == 8193


def test_explicit_initial_budget_is_never_clamped_below_request(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_MAX_STRUCTURED_NUM_PREDICT", "8192")

    class Provider:
        def __init__(self) -> None:
            self.budgets: list[int] = []

        def chat(self, request: ChatRequest) -> LLMResponse:
            self.budgets.append(int(request.options["num_predict"]))
            return _truncated()

    provider = Provider()
    with pytest.raises(LLMTruncationError):
        chat_structured(
            provider,
            Payload,
            model="synthetic",
            system_prompt="system",
            user_prompt="input",
            options={"num_predict": 12000},
        )

    assert provider.budgets == [12000]
