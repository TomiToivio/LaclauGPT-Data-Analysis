from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.codebooks import (
    Codebook,
    CodebookEntry,
    seed_memory,
    stable_codebook_id,
)
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.memory.sqlite import SQLiteMemory
from laclaugpt_data_analysis.pipeline import AnalysisProposal, analyze_record


class FakeProvider:
    def chat(self, request: ChatRequest) -> LLMResponse:
        del request
        proposal = AnalysisProposal(
            summary="Synthetic summary",
            entities=["Synthetic Actor"],
            classifications={"stance": "synthetic"},
            topics=[{"label": "Synthetic Topic"}],
            signifiers=["Synthetic Signifier"],
            formations=["Synthetic Formation"],
            uncertainty=["Needs human review"],
        )
        return LLMResponse(
            content=proposal.model_dump_json(),
            provenance=LLMCallProvenance(
                requested_mode="local",
                requested_model="fake-model",
                resolved_model="fake-model",
                actual_mode="local",
                actual_model="fake-model",
                endpoint="fake",
            ),
        )


def test_codebook_seed_uses_stable_ids_and_aliases(tmp_path):
    entry = CodebookEntry(
        kind="entity",
        label="Open Source",
        aliases=["FOSS"],
        definition="Synthetic",
    )
    codebook = Codebook(
        codebook_id="synthetic",
        version="1.0.0",
        title="Synthetic",
        entries=[entry],
    )
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    ids = seed_memory(codebook, memory)
    assert ids == [stable_codebook_id(entry)]
    resolved = memory.resolve("FOSS", "entity")
    assert resolved.decision == "EXISTING"
    assert resolved.obj_id == ids[0]
    assert memory.resolve_accepted("FOSS", "entity").obj_id == ids[0]


def test_pipeline_enriches_same_canonical_record_with_fake_provider():
    source_url = "https://example.invalid/post/1"
    record = CanonicalRecord(
        source_url=source_url,
        content={"text": "Synthetic Actor discusses technology."},
    )
    entries = [CodebookEntry(kind="entity", label="Synthetic Actor", aliases=["Actor"])]
    result = analyze_record(
        record,
        provider=FakeProvider(),
        codebook_entries=entries,
        model="fake-model",
    )
    assert result.source_url == source_url
    assert result.analysis.summary == "Synthetic summary"
    assert result.analysis.entities[0].review_status == "PROVISIONAL"
    assert result.analysis.classifications[0].source_url == source_url
    assert result.analysis.codebook_refs == ["Synthetic Actor"]
    assert result.analysis.model_runs[0]["actual_model"] == "fake-model"
    assert result.provenance[-1].metadata["stage"] == "analysis"


def test_pipeline_preserves_uncertainty_and_human_review_boundary():
    record = CanonicalRecord(
        source_url="file+sha256:synthetic",
        content={"text": "Synthetic text"},
    )
    result = analyze_record(record, provider=FakeProvider(), model="fake-model")
    assert result.analysis.uncertainty == ["Needs human review"]
    assert result.review.status is None
    assert result.analysis.formations[0].review_status == "PROVISIONAL"


def test_pipeline_uses_only_accepted_memory_for_stable_output_ids(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    entity = memory.create_stable("entity", "Synthetic Actor", state="CANONICAL")
    topic = memory.create_stable("topic", "Synthetic Topic", state="CANONICAL")
    signifier = memory.create_stable("signifier", "Synthetic Signifier", state="PROVISIONAL")

    record = CanonicalRecord(
        source_url="https://example.invalid/post/memory",
        content={"text": "Synthetic Actor discusses Synthetic Topic."},
    )
    result = analyze_record(
        record,
        provider=FakeProvider(),
        memory_store=memory,
        model="fake-model",
    )

    assert result.analysis.entities[0].entity_id == entity.obj_id
    assert result.analysis.topics[0].topic_id == topic.obj_id
    assert result.analysis.signifiers[0].object_id == "signifiers:1"
    assert result.analysis.signifiers[0].object_id != signifier.obj_id
    assert result.analysis.entities[0].review_status == "PROVISIONAL"
    assert result.provenance[-1].metadata["stable_memory_enabled"] is True
