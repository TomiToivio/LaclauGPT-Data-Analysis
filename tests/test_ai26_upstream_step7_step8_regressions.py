"""AI26 regression contracts adapted from upstream EP24 Step 7/8 incidents.

No EP24 code is imported: the tests exercise AI26's actual provider-neutral
structured-output boundary with a synthetic provider and no private data.
"""
from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ValidationError

from laclaugpt_data_analysis.llm.base import (
    ChatRequest,
    LLMCallProvenance,
    LLMResponse,
    LLMTruncationError,
)
from laclaugpt_data_analysis.llm.structured_output import chat_structured


class _RequiredClaim(BaseModel):
    claim: str
    evidence: list[str]


def _response(content: str, *, truncated: bool = False) -> LLMResponse:
    return LLMResponse(
        content=content,
        provenance=LLMCallProvenance(
            requested_mode="local",
            requested_model="synthetic",
            resolved_model="synthetic",
            actual_mode="local",
            actual_model="synthetic",
        ),
        finish_reason="length" if truncated else "stop",
        truncated=truncated,
    )


class _Sequence:
    def __init__(self, *responses: LLMResponse):
        self.responses = iter(responses)
        self.budgets: list[int] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.budgets.append(int(request.options["num_predict"]))
        return next(self.responses)


def _call(provider: _Sequence):
    return chat_structured(
        provider, _RequiredClaim, model="synthetic",
        system_prompt="Test only", user_prompt="Synthetic source",
    )


def test_length_stop_escalates_even_when_partial_json_looks_parseable() -> None:
    """A length stop cannot promote a plausible but incomplete answer."""
    provider = _Sequence(
        _response('{"claim":"premature","evidence":[]}', truncated=True),
        _response('{"claim":"supported","evidence":["synthetic quote"]}'),
    )
    parsed, response = _call(provider)
    assert parsed.claim == "supported"
    assert response.truncated is False
    assert provider.budgets == [4096, 8192]


def test_exhausted_length_stop_is_not_misclassified_as_schema_error() -> None:
    provider = _Sequence(*[
        _response('{"claim":"partial"', truncated=True) for _ in range(3)
    ])
    with pytest.raises(LLMTruncationError) as captured:
        _call(provider)
    assert captured.value.finish_reason == "length"
    assert provider.budgets == [4096, 8192, 16384]


def test_complete_but_schema_invalid_json_is_not_a_length_stop() -> None:
    """A complete invalid claim gets validation retry, not a bigger budget."""
    provider = _Sequence(
        _response('{"claim":42,"evidence":{"quote":"not a list"}}'),
        _response('{"claim":42,"evidence":{"quote":"not a list"}}'),
    )
    with pytest.raises(ValidationError):
        _call(provider)
    assert provider.budgets == [4096, 4096]


def test_complete_malformed_json_is_not_budget_exhaustion() -> None:
    provider = _Sequence(
        _response('{"claim": }'),
        _response('{"claim": }'),
    )
    with pytest.raises(json.JSONDecodeError):
        _call(provider)
    assert provider.budgets == [4096, 4096]
