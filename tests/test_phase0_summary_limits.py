import json

import pytest

import laclaugpt_process
import laclaugpt_summary


class FakeOllama:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"message": {"content": self.content}}


def _valid_summary():
    return {
        "summary": "brief",
        "claims": [],
        "actors": [],
        "entities": [],
        "topics": [],
        "signifiers": [],
        "future_visions": [],
        "governance_positions": [],
        "evidence": [],
        "uncertainty_notes": [],
    }


def test_summary_bounds_long_input_and_sets_context_options(monkeypatch):
    fake = FakeOllama(json.dumps(_valid_summary()))
    monkeypatch.setattr(laclaugpt_summary.ollama, "chat", fake.chat)
    monkeypatch.setenv("LACLAUGPT_SUMMARY_MAX_CHARS", "100")
    monkeypatch.setenv("LACLAUGPT_SUMMARY_NUM_CTX", "4096")
    monkeypatch.setenv("LACLAUGPT_SUMMARY_NUM_PREDICT", "512")

    raw, parsed = laclaugpt_summary.summarize_record(
        {"document_id": "doc-long", "metadata": {}},
        "x" * 1000,
    )

    assert raw
    call = fake.calls[0]
    assert call["options"]["num_ctx"] == 4096
    assert call["options"]["num_predict"] == 512
    assert "x" * 101 not in call["messages"][1]["content"]
    assert parsed["input_metadata"] == {
        "document_id": "doc-long",
        "original_chars": 1000,
        "sent_chars": 100,
        "truncated": True,
        "max_chars": 100,
    }


def test_summary_parse_error_keeps_raw_and_names_document(monkeypatch):
    fake = FakeOllama("")
    monkeypatch.setattr(laclaugpt_summary.ollama, "chat", fake.chat)

    with pytest.raises(laclaugpt_summary.SummaryParseError) as caught:
        laclaugpt_summary.summarize_record(
            {"document_id": "doc-empty", "metadata": {}},
            "text",
        )

    assert caught.value.raw_response == ""
    assert caught.value.metadata["document_id"] == "doc-empty"
    assert "doc-empty" in str(caught.value)
    assert "4 chars" in str(caught.value)


def test_process_persists_raw_response_on_summary_parse_failure(monkeypatch):
    writes = []

    def fail_summary(record, normalized_text):
        raise laclaugpt_summary.SummaryParseError(
            "Summary JSON parse failed for doc-1",
            raw_response="<bad-json>",
            metadata={
                "document_id": "doc-1",
                "original_chars": 12,
                "sent_chars": 12,
                "truncated": False,
                "max_chars": 24000,
            },
        )

    monkeypatch.setattr(laclaugpt_process, "summarize_record", fail_summary)
    monkeypatch.setattr(
        laclaugpt_process,
        "record_stage_failure",
        lambda source, stage, error, extra_fields=None, project_id=None: writes.append(
            {
                **(extra_fields or {}),
                f"phase0.{stage}": {"status": "error", "error": error},
            }
        ),
    )

    laclaugpt_process.run_document(
        {
            "source_url": "https://example.invalid/doc-1",
            "document_id": "doc-1",
            "normalized_text": "already here",
        },
        stage="summary",
        project_id="ai26",
    )

    assert writes[-1]["phase0_summary_raw"] == "<bad-json>"
    assert writes[-1]["phase0_summary_error_metadata"]["document_id"] == "doc-1"
    assert writes[-1]["phase0.summary"]["status"] == "error"
    assert "doc-1" in writes[-1]["phase0.summary"]["error"]
