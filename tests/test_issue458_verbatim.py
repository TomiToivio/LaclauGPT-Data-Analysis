from types import SimpleNamespace
from unittest.mock import Mock

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.stages.proposals import DiscourseProposal
from laclaugpt_data_analysis.stages.verbatim import verify_proposal


def test_correction_preserves_claims_and_bounds_calls():
    record = CanonicalRecord(source_url="https://example.org")
    record.content.text = "Workers demand a public vote on workplace automation."
    proposal = DiscourseProposal.model_validate({"demands": [
        {"label": "voice", "evidence": ["Workers demand … workplace automation.", "a fabricated phrase"]}]})
    provider = Mock()
    provider.chat.return_value = SimpleNamespace(content='{"replacements":{"demands.0.0":"Workers demand a public vote","demands.0.1":"still unlocatable"}}',
                                                 provenance=Mock(), truncated=False)
    report = verify_proposal(record, proposal, provider=provider, model="test",
                             user_prompt=record.content.text, allow_cloud_fallback=False)
    assert provider.chat.call_count == 1
    assert proposal.demands[0].evidence == ["Workers demand a public vote"]
    assert report["corrected"] == 1
    assert len(proposal.abstentions) == 1
