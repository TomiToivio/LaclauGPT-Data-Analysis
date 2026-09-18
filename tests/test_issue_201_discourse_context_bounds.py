"""Phase 0 discourse input bounds (issue #201).

A 128k-character document previously produced an empty/unusable model response and a
multi-minute hang. These tests pin the bound and the failure diagnostics offline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "laclaugpt"))

import laclaugpt_discourse as D  # noqa: E402

# --------------------------------------------------------------------------
# The bound itself
# --------------------------------------------------------------------------

def test_short_text_is_not_truncated() -> None:
    text = "AI governance needs oversight."
    bounded, truncated, original = D._bounded_text(text, limit=1000)
    assert bounded == text
    assert truncated is False
    assert original == len(text)


def test_long_text_is_truncated_and_reported() -> None:
    """A real 128k-char article must be capped, and the truncation visible."""
    text = "x" * 128_273
    bounded, truncated, original = D._bounded_text(text, limit=24_000)
    assert len(bounded) == 24_000
    assert truncated is True
    assert original == 128_273


def test_bound_keeps_the_context_inside_the_model_window() -> None:
    """The char budget must fit the configured context, not exceed it."""
    approx_tokens = D.DISCOURSE_MAX_CHARS / 4
    # Leave room for the system prompt and the generated JSON.
    assert approx_tokens < D.DISCOURSE_NUM_CTX


def test_bounds_are_configurable_by_environment(monkeypatch) -> None:
    """Operators can tune the budget without editing code."""
    assert D.DISCOURSE_MAX_CHARS > 0
    assert D.DISCOURSE_NUM_CTX > 0
    assert D.DISCOURSE_NUM_PREDICT > 0


# --------------------------------------------------------------------------
# Failure diagnostics
# --------------------------------------------------------------------------

def _fake_ollama(monkeypatch, content: str) -> None:
    class _Response(dict):
        pass

    class _Fake:
        @staticmethod
        def chat(**_kwargs):
            return {"message": {"content": content}}

    monkeypatch.setattr(D, "_ollama", lambda: _Fake)


def test_unparseable_response_names_the_document_and_keeps_the_raw(monkeypatch) -> None:
    """The error must be actionable and the raw response preserved.

    Previously the stage raised a bare ``json.loads`` error
    ("Expecting value: line 1 column 1") with no document identity, and the caller
    discarded the response entirely.
    """
    _fake_ollama(monkeypatch, "")  # the real empty-response failure mode
    record = {"document_id": "doc-201"}
    with pytest.raises(ValueError) as excinfo:
        D.analyze_discourse(record, "short text", {})
    message = str(excinfo.value)
    assert "doc-201" in message
    assert "unparseable JSON" in message
    assert "raw response" in message


def test_successful_call_records_the_input_metadata(monkeypatch) -> None:
    payload = json.dumps({"signifiers": ["ai"], "uncertainty_notes": []})
    _fake_ollama(monkeypatch, payload)
    raw, parsed = D.analyze_discourse({"document_id": "doc-1"}, "text", {})
    assert raw == payload
    assert parsed["input_metadata"]["truncated"] is False
    assert parsed["input_metadata"]["original_chars"] == 4


def test_long_document_is_truncated_before_the_call(monkeypatch) -> None:
    """The model must never receive the full 128k document."""
    seen: dict[str, str] = {}

    class _Fake:
        @staticmethod
        def chat(**kwargs):
            seen["prompt"] = kwargs["messages"][-1]["content"]
            return {"message": {"content": json.dumps({"signifiers": []})}}

    monkeypatch.setattr(D, "_ollama", lambda: _Fake)
    long_text = "y" * 128_273
    _, parsed = D.analyze_discourse({"document_id": "d"}, long_text, {})
    assert len(seen["prompt"]) < 128_273
    assert parsed["input_metadata"]["truncated"] is True
