"""Regression checks for #343 malformed JSON diagnostics (no response fragments).

One classifier, one attribute name. An earlier duplicate classifier lived beside this one and
set an attribute nothing consumed, so the diagnosis it produced never reached the durable
record; the guard at the end of this file exists so that cannot come back.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from laclaugpt_data_analysis.critical_ai import CriticalAIObject
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.llm.structured_output import (
    chat_structured,
    classify_json_decode_failure,
)


def _diagnose(raw):
    try:
        json.loads(raw)
    except json.JSONDecodeError as error:
        return classify_json_decode_failure(raw, error)
    raise AssertionError("fixture must be malformed")


def test_trailing_comma_classification():
    result = _diagnose('{"some_private_text":"SECRET",}')
    assert result["decode_shape"] == "trailing_comma"
    assert "SECRET" not in str(result)


def test_truncated_response_classification():
    assert _diagnose('{"key": [1, 2')["decode_shape"] == "possibly_truncated"


def test_prose_wrapper_classification():
    assert _diagnose('Here is the JSON: {"key":1}')["decode_shape"] == "prose_wrapper"


def test_single_quote_classification():
    assert _diagnose("{'key': 'private'}")["decode_shape"] == "single_quotes_possible"


def test_the_classification_carries_imbalance_counts_without_any_response_text():
    """A truncated response leaves an open structure; a mis-punctuated one balances."""
    truncated = _diagnose('{"key": [1, 2')
    assert truncated["decode_brace_balance"] == 1
    assert truncated["decode_bracket_balance"] == 1

    punctuated = _diagnose('{"a": 1,}')
    assert punctuated["decode_brace_balance"] == 0
    assert punctuated["decode_bracket_balance"] == 0

    assert "SECRET" not in str(_diagnose('{"some_private_text":"SECRET",}'))


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


def test_a_decode_failure_attaches_what_the_worker_actually_reads():
    provider = FakeProvider(["Sure, here is the JSON: " + '{"types": ["model"]}'])
    with pytest.raises(Exception) as caught:
        chat_structured(
            provider,
            CriticalAIObject,
            model="synthetic",
            system_prompt="system",
            user_prompt="user",
        )
    diagnosis = getattr(caught.value, "decode_diagnostics", None)
    assert diagnosis is not None, "the worker reads decode_diagnostics, so it must be set"
    assert diagnosis["decode_shape"] == "prose_wrapper"
    assert len(provider.calls) == 2, "the existing one-retry contract is unchanged"


def test_a_valid_response_is_untouched():
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


def test_there_is_exactly_one_decode_classifier_and_one_attribute_name():
    """The duplicate that caused this file's header note must not come back."""
    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src"
        / "laclaugpt_data_analysis"
        / "llm"
        / "structured_output.py"
    ).read_text(encoding="utf-8")
    assert source.count("def classify_json") == 1, "one classifier, not two"
    assert "json_failure" not in source, "one attribute name"

    worker = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src"
        / "laclaugpt_data_analysis"
        / "distributed_worker.py"
    ).read_text(encoding="utf-8")
    assert 'getattr(exc, "decode_diagnostics", None)' in worker
    assert "exc.decode_diagnostics = " in source, (
        "the attribute the worker reads must be the attribute the producer sets"
    )
