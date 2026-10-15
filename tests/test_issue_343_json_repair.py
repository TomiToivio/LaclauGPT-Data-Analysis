"""Issue #343: bounded structural repair for malformed model JSON.

The AI26 worker's captured failures (``ai26__analysis_failures.response_raw``) show
the ``JSONDecodeError`` class is not truncation and not a fence/prose problem: 345 of
353 captured decodes finished with ``finish_reason=stop``, fence stripping alone
recovers none of them, and the failing character is usually a backslash or a colon -
damage in the JSON skeleton, not in the research text.

These tests pin the repair classes that were measured, and - at least as important -
pin that the repair is narrow: valid JSON is returned byte-identical, and no
alphanumeric content is ever invented.
"""
from __future__ import annotations

import json
import re
from typing import Any

import pytest
from pydantic import BaseModel

from laclaugpt_data_analysis.llm.json_repair import (
    JSON_REPAIR_ENV,
    first_json_value,
    join_repairs,
    json_repair_enabled,
    repair_json_text,
    repaired_candidate,
)
from laclaugpt_data_analysis.llm.structured_output import (
    parse_structured,
    strip_code_fences,
)


class _Payload(BaseModel):
    """Small schema: the repair is about JSON syntax, not about any study schema."""

    label: str = ""
    items: list[str] = []
    note: str = ""


# ------------------------------------------------------------------ the classes

def test_repairs_a_quote_the_model_over_escaped_outside_a_string() -> None:
    """Measured ``Expecting value`` at a backslash: ``"key": \\\"value...``."""
    broken = '{"label": \\"a summary.", "items": []}'

    repaired, applied = repair_json_text(broken)

    assert json.loads(repaired)["label"] == "a summary."
    assert "structural_skeleton" in applied


def test_repairs_a_duplicated_colon() -> None:
    """Measured ``Expecting ',' delimiter`` at a second colon: ``"key":: {...}``."""
    broken = '{"label":: "two colons", "items": []}'

    repaired, applied = repair_json_text(broken)

    assert json.loads(repaired)["label"] == "two colons"
    assert "structural_skeleton" in applied


def test_repairs_a_stray_token_between_members() -> None:
    """Measured ``Expecting property name`` at a lone underscore between members."""
    broken = '{"label": "x", "items": ["a"],_\n  "note": "y"}'

    repaired, _ = repair_json_text(broken)

    assert json.loads(repaired) == {"label": "x", "items": ["a"], "note": "y"}


def test_repairs_a_missing_comma_between_members() -> None:
    broken = '{"label": "x" "items": ["a"]}'

    repaired, _ = repair_json_text(broken)

    assert json.loads(repaired) == {"label": "x", "items": ["a"]}


def test_repairs_a_trailing_comma() -> None:
    """The one class the simplest repair already covers (54 of 353 measured)."""
    broken = '{"label": "x", "items": ["a",],}'

    repaired, _ = repair_json_text(broken)

    assert json.loads(repaired) == {"label": "x", "items": ["a"]}


def test_repairs_extra_data_after_a_complete_object() -> None:
    """Measured ``Extra data``: a second fragment after a complete value."""
    broken = '{"label": "x", "items": []},\n  "label": ["y"]'

    repaired, applied = repair_json_text(broken)

    assert json.loads(repaired) == {"label": "x", "items": []}
    assert "first_value" in applied


def test_a_raw_control_character_inside_a_string_is_escaped_losslessly() -> None:
    """Measured ``Invalid control character``: the newline must survive, not vanish."""
    broken = '{"label": "first line\nsecond line", "items": []}'

    repaired, _ = repair_json_text(broken)

    assert json.loads(repaired)["label"] == "first line\nsecond line"


def test_strip_one_surrounding_code_fence() -> None:
    assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_first_json_value_returns_none_when_there_is_no_complete_value() -> None:
    assert first_json_value('{"a": ') is None


# ------------------------------------------------------------ narrowness proofs

VALID_DOCUMENTS = [
    '{"a": 1}',
    '{"a": "x:y", "b": ["1,2", "3"]}',
    '{"a": "true", "b": null, "c": -1.5e3}',
    '{"n": [1, 2.5e-3, -7, 0], "s": "a:b,c", "e": "", "l": []}',
    '{"text": "line\\nbreak", "u": "\\u00e9", "q": "say \\"hi\\""}',
    '{"deep": {"a": [{"b": "c,d"}]}, "t": true}',
    json.dumps({"label": "under_score", "items": ["a_b", "c-d"]}),
]


@pytest.mark.parametrize("document", VALID_DOCUMENTS)
def test_valid_json_is_never_altered(document: str) -> None:
    """The repair must be a no-op on well-formed output, whatever is in the strings."""
    assert repair_json_text(document) == (document, ())
    assert repaired_candidate(document) == (document, ())


BROKEN_DOCUMENTS = [
    '{"label": \\"x", "items": []}',
    '{"label":: "x", "items": []}',
    '{"label": "x",_\n  "items": ["a"]}',
    '{"label": "x" "items": ["a"]}',
    '{"label": "x", "items": ["a",],}',
    '{"label": "x", "items": []},\n  "label": ["y"]',
    '{"label": "a\nb", "items": []}',
]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9]+", text))


def _decoded_strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        out: list[str] = []
        for key, value in node.items():
            out.extend(_decoded_strings(key))
            out.extend(_decoded_strings(value))
        return out
    if isinstance(node, list):
        out = []
        for item in node:
            out.extend(_decoded_strings(item))
        return out
    return []


@pytest.mark.parametrize("document", BROKEN_DOCUMENTS)
def test_the_repair_invents_no_content(document: str) -> None:
    """Repair may drop stray tokens and add punctuation - never new words or numbers.

    Checked on the *decoded* content, so the escape sequences the repair adds around a
    raw control character (`\\n`) are not mistaken for invented text.
    """
    repaired, applied = repair_json_text(document)

    assert applied, "a broken document must report what was applied"
    invented = set()
    for value in _decoded_strings(json.loads(repaired)):
        invented |= _tokens(value) - _tokens(document)
    assert not invented, f"the repair invented content: {sorted(invented)}"


def test_repairs_are_named_for_the_log() -> None:
    _, applied = repair_json_text('{"label":: "x"}')

    assert join_repairs(applied) == ", ".join(applied)
    assert "structural_skeleton" in applied


# --------------------------------------------------------------- the parse path

def test_parse_structured_recovers_a_repairable_payload() -> None:
    payload = parse_structured('{"label": \\"x", "items": [], "note": "ok"}', _Payload)

    assert payload.label == "x"
    assert payload.note == "ok"


def test_parse_structured_still_rejects_a_genuinely_broken_payload() -> None:
    """A truncation mid-value is not repairable and must stay a hard failure."""
    with pytest.raises(json.JSONDecodeError):
        parse_structured('{"label": "x", "items": ["a", "b', _Payload)


def test_parse_structured_still_rejects_a_shape_error() -> None:
    """Repair fixes syntax only: a wrong *shape* must still fail validation."""
    with pytest.raises(Exception) as excinfo:
        parse_structured('{"label": 5, "items": {"not": "a list"}, "note": "x"}', _Payload)

    assert "validation error" in str(excinfo.value).lower()


def test_env_switch_disables_the_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(JSON_REPAIR_ENV, "0")

    assert json_repair_enabled() is False
    with pytest.raises(json.JSONDecodeError):
        parse_structured('{"label":: "x"}', _Payload)


def test_chat_structured_does_not_spend_the_retry_on_a_repairable_response() -> None:
    """The point of the repair: one model call, not two, for a syntax slip."""
    from laclaugpt_data_analysis.llm.base import (
        ChatRequest,
        LLMCallProvenance,
        LLMResponse,
    )
    from laclaugpt_data_analysis.llm.structured_output import chat_structured

    class _Provider:
        def __init__(self) -> None:
            self.calls: list[ChatRequest] = []

        def chat(self, request: ChatRequest) -> LLMResponse:
            self.calls.append(request)
            return LLMResponse(
                content='{"label":: "recovered", "items": []}',
                provenance=LLMCallProvenance(
                    requested_mode="local-ollama",
                    requested_model=request.model,
                    resolved_model=request.model,
                    actual_mode="local-ollama",
                    actual_model=request.model,
                ),
                finish_reason="stop",
            )

    provider = _Provider()
    payload, _response = chat_structured(
        provider,  # type: ignore[arg-type]
        _Payload,
        model="synthetic-model",
        system_prompt="system",
        user_prompt="user",
    )

    assert payload.label == "recovered"
    assert len(provider.calls) == 1, "a repairable response must not consume the retry"


def test_the_llm_package_reexports_the_shared_fence_stripper() -> None:
    from laclaugpt_data_analysis import llm

    assert callable(llm.strip_code_fences)
    assert llm.strip_code_fences is strip_code_fences
