"""#435 acceptance 1: AI26's structured-output boundary must separate its failure classes.

Upstream ports (#403/#409) distinguish a *truncated* response from a *malformed* one and from a
*schema-invalid* one, because each needs different handling: truncation is a budget signal, malformed JSON
may admit one bounded structural repair, and a complete-but-wrong object is the model's answer being refused.
The four outcomes below are asserted against the real boundary (``parse_structured``), not a stand-in, and
none of them may come back as a successfully parsed object carrying evidence.

Synthetic by design: no model call, no network, no private text.
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ValidationError

from laclaugpt_data_analysis.llm.structured_output import (
    classify_json_decode_failure,
    parse_structured,
)


class _Evidence(BaseModel):
    quote: str
    exact: bool = False


class _Proposal(BaseModel):
    analysis_markdown: str = ""
    evidence: list[_Evidence] = []


def test_truncated_output_is_classified_as_truncation_and_yields_no_object():
    content = '{"analysis_markdown": "the discourse is articulated around"'  # cut inside a string
    with pytest.raises(json.JSONDecodeError) as caught:
        parse_structured(content, _Proposal)

    # The classifier is the boundary's own labelling of the failure; ask it directly rather than
    # assuming a provider response object was attached (parse_structured has none to attach).
    diagnostics = classify_json_decode_failure(content, caught.value)
    assert diagnostics["decode_shape"] == "possibly_truncated", diagnostics
    assert diagnostics.get("decode_response_chars") == len(content)


def test_malformed_but_complete_json_is_not_reported_as_truncation():
    content = '{"analysis_markdown": }'  # closes its scope, so it was not cut off
    with pytest.raises(json.JSONDecodeError) as caught:
        parse_structured(content, _Proposal)

    assert classify_json_decode_failure(content, caught.value)["decode_shape"] != "possibly_truncated"


def test_complete_json_that_violates_the_schema_is_a_validation_error():
    content = json.dumps({"analysis_markdown": "fine", "evidence": "not-a-list-of-objects"})
    with pytest.raises(ValidationError):
        parse_structured(content, _Proposal)


def test_empty_response_is_its_own_class_not_a_grammar_error():
    from laclaugpt_data_analysis.llm.base import LLMEmptyResponseError

    with pytest.raises(LLMEmptyResponseError):
        parse_structured("   ", _Proposal)


def test_abstention_parses_with_no_evidence_so_it_cannot_be_counted_as_evidence_backed():
    proposal = parse_structured(
        json.dumps({"analysis_markdown": "no verbatim evidence found", "evidence": []}),
        _Proposal,
    )
    assert proposal.evidence == []
    assert proposal.analysis_markdown.strip() != ""
