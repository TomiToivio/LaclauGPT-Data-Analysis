"""Source-grounding regression tests for the evidence gate.

Ported intent from LaclauGPT-Multimodal-Analysis #285 (issue #372): a model's quotation counts as
evidence only when the code can point at the characters it claims to quote. That repository fixed a
source-laundering path by refusing quotations from derived text; AI26's mechanism is different and
stronger -- it locates the quote in the ORIGINAL source and records character offsets plus an
`exact` flag -- but the function that decides all of this, `locate_quote`, had no tests at all.

These tests pin the properties that matter for the Phase 1 evidence contract:

* a verbatim quotation is located, and the returned span slices the source as written;
* whitespace re-wrapping and case changes do not reject a genuine quotation (models re-flow text);
* a paraphrase is NOT located, so it cannot masquerade as a quotation;
* a fragment shorter than the minimum is refused even when it matches, because a stray phrase is
  not evidence of anything;
* `evidence_ids` records a non-verbatim quote as provisional with `exact=False` and no offsets --
  it drops nothing, and it never removes evidence already attached.
"""

from __future__ import annotations

from datetime import UTC, datetime

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.stages.evidence import evidence_ids, locate_quote
from laclaugpt_data_analysis.stages.proposals import _MIN_QUOTE_CHARS

SOURCE = "The ministry confirmed the timetable for the audit would not change."


def _record(text: str = SOURCE) -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/issue-372/1",
        raw_capture={"payload": {"synthetic": True}},
        source={"platform": "synthetic", "created_at": datetime(2026, 10, 19, tzinfo=UTC)},
        content={"text": text},
    )


class TestLocateQuote:
    def test_a_verbatim_quotation_returns_offsets_that_slice_the_source(self):
        quote = "confirmed the timetable"
        start, end = locate_quote(SOURCE, quote)
        assert start is not None and end is not None
        assert SOURCE[start:end] == quote

    def test_rewrapped_whitespace_does_not_reject_a_genuine_quotation(self):
        source = "the  ministry\nconfirmed   the timetable"
        quote = "the ministry confirmed the timetable"
        start, end = locate_quote(source, quote)
        assert start is not None and end is not None
        # the span covers the original characters, whitespace included
        assert " ".join(source[start:end].split()) == quote

    def test_case_differences_do_not_reject_a_genuine_quotation(self):
        start, end = locate_quote(SOURCE, "THE MINISTRY CONFIRMED")
        assert start is not None and end is not None
        assert SOURCE[start:end] == "The ministry confirmed"

    def test_a_paraphrase_is_not_located(self):
        assert locate_quote(SOURCE, "the ministry said the audit schedule was fixed") == (None, None)

    def test_a_fragment_shorter_than_the_minimum_is_refused_even_when_it_matches(self):
        fragment = "the audit w"
        assert len(fragment) == _MIN_QUOTE_CHARS - 1
        assert fragment in SOURCE
        assert locate_quote(SOURCE, fragment) == (None, None)

    def test_empty_inputs_are_not_located(self):
        assert locate_quote("", "confirmed the timetable") == (None, None)
        assert locate_quote(SOURCE, "") == (None, None)
        assert locate_quote(SOURCE, "   ") == (None, None)


class TestEvidenceRecording:
    def test_a_verbatim_quote_is_recorded_with_offsets_and_provisional_status(self):
        record = _record()
        ids = evidence_ids(record, ["confirmed the timetable"], "step6")
        assert ids == ["step6:evidence:1"]
        item = record.evidence[0]
        assert item.quote == "confirmed the timetable"
        assert item.start_offset is not None and item.end_offset is not None
        assert SOURCE[item.start_offset:item.end_offset] == item.quote
        assert item.metadata["exact"] is True
        assert item.metadata["review_status"] == "PROVISIONAL"

    def test_a_paraphrase_is_recorded_but_marked_inexact_rather_than_dropped(self):
        record = _record()
        evidence_ids(record, ["the audit schedule was fixed by the ministry"], "step6")
        item = record.evidence[0]
        assert item.start_offset is None and item.end_offset is None
        assert item.metadata["exact"] is False
        assert item.metadata["review_status"] == "PROVISIONAL"

    def test_recording_appends_and_never_removes_existing_evidence(self):
        record = _record()
        evidence_ids(record, ["confirmed the timetable"], "step6")
        before = len(record.evidence)
        ids = evidence_ids(record, ["the audit would not change"], "step6")
        assert len(record.evidence) == before + 1
        assert ids == [f"step6:evidence:{before + 1}"]
        assert record.evidence[0].quote == "confirmed the timetable"

    def test_blank_quotes_are_skipped_without_creating_evidence(self):
        record = _record()
        assert evidence_ids(record, ["", "   "], "step6") == []
        assert record.evidence == []
