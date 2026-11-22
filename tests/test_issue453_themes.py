from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.stages.postprocess import postprocess_record
from laclaugpt_data_analysis.stages.proposals import DiscourseProposal, SummaryProposal


def test_only_evidenced_themes_survive_projection_and_round_trip():
    record = CanonicalRecord(source_url="https://example.org/work")
    record.content.text = "Workers demand a vote before the factory automates their jobs."
    proposal = DiscourseProposal.model_validate({"themes": [
        {"label": "Worker control", "evidence": [record.content.text]},
        {"label": "An unrelated interpretation", "evidence": ["Invented quotation"]},
    ]})
    result = postprocess_record(record, SummaryProposal(topics=["Automation"]), proposal)
    restored = CanonicalRecord.model_validate_json(result.model_dump_json())
    theme, = restored.analysis.themes
    assert (theme.kind, theme.label, theme.review_status) == ("theme", "Worker control", "PROVISIONAL")
    assert theme.evidence_ids[0] in {item.evidence_id for item in restored.evidence}
    assert restored.human_readable.sections["themes"] == "Worker control"
    result = postprocess_record(restored, SummaryProposal(topics=["Automation"]), DiscourseProposal())
    assert result.analysis.themes == []
