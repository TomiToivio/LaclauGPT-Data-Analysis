"""Regression checks for #343 malformed JSON diagnostics (no response fragments)."""
import json

from laclaugpt_data_analysis.llm.structured_output import classify_json_decode_failure


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
