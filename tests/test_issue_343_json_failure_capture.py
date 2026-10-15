"""#343: name why a structured response could not be parsed.

The pipeline logged only ``JSONDecodeError``, which is not enough to choose a fix: a prose
wrapper needs stripping, a length stop needs a bigger budget, and a trailing comma needs a
repair. These tests pin the classification, the value-elided excerpt, and the wiring that
attaches both to the exception the worker already records.
"""
from __future__ import annotations

import json

import pytest

from laclaugpt_data_analysis.critical_ai import CriticalAIObject
from laclaugpt_data_analysis.llm.base import (
    ChatRequest,
    LLMCallProvenance,
    LLMResponse,
)
from laclaugpt_data_analysis.llm.structured_output import (
    chat_structured,
    classify_json_failure,
    sanitize_structured_excerpt,
)

BACKSLASH = chr(92)
QUOTE = chr(34)


def _decode_error(text: str) -> json.JSONDecodeError:
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return exc
    raise AssertionError("the sample was supposed to fail to parse")


class FakeProvider:
    """Minimal provider: returns the queued contents in order."""

    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)
        self.calls: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.calls.append(request)
        index = min(len(self.calls) - 1, len(self.contents) - 1)
        return LLMResponse(
            content=self.contents[index],
            provenance=LLMCallProvenance(
                requested_mode="local",
                requested_model="synthetic",
                resolved_model="synthetic",
                actual_mode="local",
                actual_model="synthetic",
            ),
            finish_reason="stop",
        )


def test_the_failure_modes_are_named_from_the_response_shape() -> None:
    cases = {
        "empty_response": "",
        "fences_only": "```json" + chr(10) + "```",
        "prose_wrapped": "Sure, here is the JSON: " + '{"a": 1}',
        "trailing_text": '{"a": 1} - and that is why.',
        "unbalanced_structure": '{"a": 1, "b"',
        "trailing_comma": '{"a": 1,}',
        "single_quoted_key": "{'a': 1}",
        "unquoted_key": "{a: 1}",
        "invalid_escape": '{"a": "' + BACKSLASH + 'x41"}',
    }
    for expected, text in cases.items():
        diagnosis = classify_json_failure(text, _decode_error(text))
        assert diagnosis["mode"] == expected, (expected, diagnosis)


def test_the_diagnosis_carries_the_position_and_the_structural_counts() -> None:
    text = '{"a": 1, "b"'
    diagnosis = classify_json_failure(text, _decode_error(text))
    assert diagnosis["chars"] == len(text)
    assert diagnosis["brace_balance"] == 1
    assert diagnosis["bracket_balance"] == 0
    assert diagnosis["position"] is not None


def test_the_excerpt_keeps_schema_keys_and_elides_every_value() -> None:
    secret = "SYNTHETIC-SOURCE-TEXT-THAT-MUST-NOT-BE-LOGGED"
    text = '{"schema_version": "critical-ai-v1", "summary": "' + secret + '"}'
    excerpt = sanitize_structured_excerpt(text)
    assert "schema_version" in excerpt
    assert "critical-ai-v1" not in excerpt
    assert secret not in excerpt
    assert "<elided>" in excerpt


def test_the_excerpt_marks_truncation_explicitly() -> None:
    excerpt = sanitize_structured_excerpt('{"a": "' + "x" * 900 + '"}', limit=100)
    assert "more chars>" in excerpt


def test_a_decode_failure_is_classified_and_attached_to_the_exception() -> None:
    provider = FakeProvider(["Here you go: " + '{"types": ["model"]}'])
    with pytest.raises(Exception) as caught:
        chat_structured(
            provider,
            CriticalAIObject,
            model="synthetic",
            system_prompt="system",
            user_prompt="user",
        )
    diagnosis = getattr(caught.value, "json_failure", None)
    assert diagnosis is not None, "the decode failure must carry its classification"
    assert diagnosis["mode"] == "prose_wrapped"
    assert len(provider.calls) == 2, "the existing one-retry contract is unchanged"


def test_the_raw_payload_is_still_available_to_an_operator() -> None:
    raw = "Here you go: " + '{"types": ["model"]}'
    provider = FakeProvider([raw])
    with pytest.raises(Exception) as caught:
        chat_structured(
            provider,
            CriticalAIObject,
            model="synthetic",
            system_prompt="system",
            user_prompt="user",
        )
    assert getattr(caught.value, "response_raw", None) == raw


def test_a_valid_response_is_untouched_and_raises_nothing() -> None:
    provider = FakeProvider(['{"types": ["model"]}'])
    parsed, _ = chat_structured(
        provider,
        CriticalAIObject,
        model="synthetic",
        system_prompt="system",
        user_prompt="user",
    )
    assert parsed.types == ["model"]
    assert len(provider.calls) == 1
