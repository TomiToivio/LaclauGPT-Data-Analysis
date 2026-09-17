"""Evidence spans must be verified against the source, or explicitly flagged inexact.

Phase 3 blocker (issue #53): ``_evidence_ids`` wrapped model-proposed strings as
``llm_proposed_source_evidence`` without ever locating them in ``content.text``.
Measured on the live AI26 corpus: 412 evidence items, **0 with offsets**, only
**2.4 %** verbatim in their own source, mean token overlap 0.51 — i.e. paraphrases
presented as quotations.

Policy (Tomi's decision): flag-and-count. A quote that cannot be located in the
source is KEPT (nothing is dropped silently) but marked ``exact=False`` so the rate
is measurable and the item is never citable as a verbatim quotation. This mirrors
``dna_statement_coding._validated_span`` and ``claims.py``, which already enforce
verbatim-ness on their own paths.
"""
from datetime import UTC, datetime

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.canonical_pipeline import _evidence_ids
from laclaugpt_data_analysis.pipeline import _evidence_ids as _pipeline_evidence_ids

SOURCE_TEXT = "AI should serve democratic society. Markets alone will not decide."


def synthetic_record() -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/evidence/1",
        source={"platform": "synthetic", "created_at": datetime(2026, 9, 17, tzinfo=UTC)},
        content={"title": "Synthetic AI debate", "text": SOURCE_TEXT},
    )


# --------------------------------------------------------------------------
# exact=True: a verbatim quotation is located and marked exact
# --------------------------------------------------------------------------

def test_verbatim_quote_is_located_and_marked_exact() -> None:
    record = synthetic_record()
    ids = _evidence_ids(record, ["AI should serve democratic society."], "signifier:1")
    assert len(ids) == 1

    evidence = next(e for e in record.evidence if e.evidence_id == ids[0])
    assert evidence.metadata["exact"] is True
    assert evidence.start_offset is not None and evidence.end_offset is not None
    assert SOURCE_TEXT[evidence.start_offset : evidence.end_offset] == evidence.quote


def test_offsets_slice_back_to_the_quote_exactly() -> None:
    """The strongest guarantee: the stored offsets reproduce the stored quote."""
    record = synthetic_record()
    quote = "Markets alone will not decide."
    ids = _evidence_ids(record, [quote], "signifier:1")

    evidence = next(e for e in record.evidence if e.evidence_id == ids[0])
    assert SOURCE_TEXT[evidence.start_offset : evidence.end_offset] == quote


# --------------------------------------------------------------------------
# exact=False: a paraphrase is preserved but flagged, never silently accepted
# --------------------------------------------------------------------------

def test_paraphrase_is_kept_but_flagged_inexact() -> None:
    record = synthetic_record()
    paraphrase = "AI ought to be democratic rather than market-driven."
    ids = _evidence_ids(record, [paraphrase], "signifier:1")

    assert len(ids) == 1, "a non-verbatim quote must not be dropped silently"
    evidence = next(e for e in record.evidence if e.evidence_id == ids[0])
    assert evidence.quote == paraphrase
    assert evidence.metadata["exact"] is False
    assert evidence.start_offset is None
    assert evidence.end_offset is None


def test_inexact_evidence_remains_citable_as_provisional() -> None:
    """Flagged, not discarded: the audit trail must survive for measurement."""
    record = synthetic_record()
    _evidence_ids(record, ["Something entirely unrelated to the source."], "signifier:1")

    evidence = record.evidence[0]
    assert evidence.metadata["review_status"] == "PROVISIONAL"
    assert evidence.metadata["exact"] is False


# --------------------------------------------------------------------------
# accounting: the inexact count is what makes the rate measurable
# --------------------------------------------------------------------------

def test_exact_count_is_recoverable_from_the_record() -> None:
    """The reportable metric: exact_true / total, computed from evidence metadata."""
    record = synthetic_record()
    _evidence_ids(record, ["AI should serve democratic society."], "signifier:1")
    _evidence_ids(record, ["A paraphrase that is not in the source at all."], "signifier:2")
    _evidence_ids(record, ["Markets alone will not decide."], "signifier:3")

    exact = [e for e in record.evidence if e.metadata.get("exact") is True]
    inexact = [e for e in record.evidence if e.metadata.get("exact") is False]
    assert len(record.evidence) == 3
    assert len(exact) == 2
    assert len(inexact) == 1
    assert all("exact" in e.metadata for e in record.evidence), "every item must be classified"


# --------------------------------------------------------------------------
# robustness
# --------------------------------------------------------------------------

def test_whitespace_and_empty_quotes() -> None:
    record = synthetic_record()
    ids = _evidence_ids(record, ["", "   ", "\n"], "signifier:1")
    assert ids == []
    assert record.evidence == []


def test_whitespace_normalised_quote_still_matches() -> None:
    """Line-wrapped model output must still be locatable."""
    record = synthetic_record()
    ids = _evidence_ids(record, ["AI should serve   democratic society."], "signifier:1")
    evidence = next(e for e in record.evidence if e.evidence_id == ids[0])
    assert evidence.metadata["exact"] is True


def test_short_quote_is_not_treated_as_verbatim_by_accident() -> None:
    """A 4-character string can match by chance; it must not claim to be evidence."""
    record = synthetic_record()
    ids = _evidence_ids(record, ["AI"], "signifier:1")
    evidence = next(e for e in record.evidence if e.evidence_id == ids[0])
    assert evidence.metadata["exact"] is False


def test_missing_content_text_never_raises() -> None:
    """A record with no text must flag inexact rather than crash the pipeline."""
    record = CanonicalRecord(source_url="https://example.invalid/empty/1", content={"text": ""})
    ids = _evidence_ids(record, ["anything at all"], "signifier:1")
    evidence = next(e for e in record.evidence if e.evidence_id == ids[0])
    assert evidence.metadata["exact"] is False


# --------------------------------------------------------------------------
# both pipeline entry points must behave identically
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "impl",
    [_evidence_ids, _pipeline_evidence_ids],
    ids=["canonical_pipeline", "pipeline"],
)
def test_both_entry_points_apply_the_same_policy(impl) -> None:
    record = synthetic_record()
    ids = impl(record, ["AI should serve democratic society."], "signifier:1")
    evidence = next(e for e in record.evidence if e.evidence_id == ids[0])
    assert evidence.metadata["exact"] is True
    assert SOURCE_TEXT[evidence.start_offset : evidence.end_offset] == evidence.quote

    record2 = synthetic_record()
    ids2 = impl(record2, ["A pure paraphrase with no verbatim overlap."], "signifier:1")
    evidence2 = next(e for e in record2.evidence if e.evidence_id == ids2[0])
    assert evidence2.metadata["exact"] is False
