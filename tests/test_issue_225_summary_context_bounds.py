"""Phase 0 summary input bounds (issue #225).

The summary stage runs before every other LLM stage, so an unbounded document here
blocked whole documents. A 129k-character article produced an empty response and a bare
"Expecting value: line 1 column 1 (char 0)".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "laclaugpt"))

import laclaugpt_summary as S  # noqa: E402


class _FakeOllama:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"message": {"content": self.content}}


def _install(monkeypatch, content: str) -> _FakeOllama:
    fake = _FakeOllama(content)
    monkeypatch.setattr(S, "ollama", fake)
    return fake


# --------------------------------------------------------------------------
# The bound
# --------------------------------------------------------------------------

def test_short_text_is_not_truncated() -> None:
    text = "AI governance needs oversight."
    bounded, truncated = S._bounded_text(text)
    assert bounded == text
    assert truncated is False


def test_long_text_is_truncated_and_reported() -> None:
    """The real failing document was 129,134 characters."""
    text = "x" * 129_134
    bounded, truncated = S._bounded_text(text)
    assert len(bounded) == S.SUMMARY_MAX_CHARS
    assert truncated is True


def test_the_bound_fits_inside_the_context_window() -> None:
    assert S.SUMMARY_MAX_CHARS / 4 < S.SUMMARY_NUM_CTX


def test_the_model_never_receives_the_full_long_document(monkeypatch) -> None:
    fake = _install(monkeypatch, json.dumps({"summary": "ok"}))
    long_text = "y" * 129_134
    _, parsed = S.summarize_record({"document_id": "d"}, long_text)
    sent = fake.calls[0]["messages"][-1]["content"]
    assert len(sent) < 129_134
    assert parsed["input_metadata"]["truncated"] is True
    assert parsed["input_metadata"]["original_chars"] == 129_134


def test_explicit_context_options_are_sent(monkeypatch) -> None:
    fake = _install(monkeypatch, json.dumps({"summary": "ok"}))
    S.summarize_record({"document_id": "d"}, "short text")
    options = fake.calls[0]["options"]
    assert options["num_ctx"] == S.SUMMARY_NUM_CTX
    assert options["num_predict"] == S.SUMMARY_NUM_PREDICT


# --------------------------------------------------------------------------
# Failure diagnostics
# --------------------------------------------------------------------------

def test_empty_response_names_the_document_and_keeps_the_raw(monkeypatch) -> None:
    """The real failure mode: an empty message.

    Previously this surfaced as a bare "Expecting value: line 1 column 1 (char 0)"
    with no document identity and no retained output.
    """
    _install(monkeypatch, "")
    with pytest.raises(S.SummaryParseError) as excinfo:
        S.summarize_record({"document_id": "doc-225"}, "text")
    assert "doc-225" in str(excinfo.value)
    assert excinfo.value.raw_response == ""
    assert excinfo.value.metadata["document_id"] == "doc-225"
    assert excinfo.value.metadata["truncated"] is False


def test_metadata_reports_the_truncation_on_failure(monkeypatch) -> None:
    _install(monkeypatch, "")
    with pytest.raises(S.SummaryParseError) as excinfo:
        S.summarize_record({"document_id": "d"}, "z" * 129_134)
    assert excinfo.value.metadata["input_chars"] == 129_134
    assert excinfo.value.metadata["sent_chars"] == S.SUMMARY_MAX_CHARS
    assert excinfo.value.metadata["truncated"] is True


def test_parse_error_is_a_value_error() -> None:
    """Keeps compatibility with the generic ``except Exception`` in the pipeline."""
    assert issubclass(S.SummaryParseError, ValueError)


def test_document_label_falls_back_to_url() -> None:
    assert S._document_label({"source_url": "https://example.invalid/a"}) == "https://example.invalid/a"
    assert S._document_label({"metadata": {"url": "https://example.invalid/b"}}) == "https://example.invalid/b"
    assert S._document_label({}) == "<unknown>"
