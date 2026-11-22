"""#450 and #453 executed per docs/AI26_OPEN_DECISIONS.md (D1 and D3, 2026-11-22).

Both fields were declared and exported but produced nothing: `discourses` empty in
5 302 of 5 302 stored analyses, `themes` the same. The memo's decisions were to
retire `discourses` (D1) and to stop asking the model for `themes` (D3) rather than
keep a column that can never fill.

The storage fields stay reserved so 5 302 stored records keep loading; what changes
is that the instrument no longer asks for text it discards and no reviewer is handed
a permanently empty column.
"""

from pathlib import Path

from laclaugpt_data_analysis.canonical import AnalysisSection
from laclaugpt_data_analysis.field_contract import UNPRODUCED_FIELDS

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "src" / "laclaugpt_data_analysis" / "prompts" / "laclau" / "document_analysis_v1.md"


def test_the_prompt_no_longer_asks_for_themes():
    prompt = PROMPT.read_text(encoding="utf-8")
    assert "topics/themes" not in prompt, "D3: the schema discards themes, so do not ask for them"
    assert "topics" in prompt, "topics is populated and must still be requested"


def test_themes_stays_reserved_in_the_record():
    """D3 keeps the field: removing it would break stored records, not just new output."""
    assert "themes" in AnalysisSection.model_fields


def test_the_review_export_column_is_still_present_pending_the_interchange_fix():
    """D1 is decided, but removing the column breaks the round-trip contract.

    `tools/verify_contracts.py` reports `KeyError: 'discourses'` once the column is
    dropped: the CSV/JSONL/sqlite adapters in `interchange.py` reconstruct the logical
    record from the legacy projection and require the key to exist. Retiring the column
    therefore needs that path updated in the same change, which is a separate, scoped
    follow-up -- so the column stays for now and #450 is not claimed resolved.
    """
    source = (ROOT / "src" / "laclaugpt_data_analysis" / "research_record.py").read_text(encoding="utf-8")
    assert '"discourses"' in source, "column removed without fixing the adapter round trip"


def test_the_contract_records_both_decisions_as_retired():
    for field in ("discourses", "themes"):
        assert field in UNPRODUCED_FIELDS
        decision = UNPRODUCED_FIELDS[field].decision
        assert decision.startswith("RETIRED"), (
            f"{field} still reads as an open question: {decision[:60]!r}"
        )
        assert "AI26_OPEN_DECISIONS.md" in decision
