from pydantic import BaseModel

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.llm.base import LLMResponse
from laclaugpt_data_analysis.llm.routing import resolve_model
from laclaugpt_data_analysis.memory import MemoryEntry, SQLiteMemoryStore, resolve, stable_id
from laclaugpt_data_analysis.pipeline import AnalysisProposal, analyze_record


class FakeProvider:
    def structured(self, model_cls, **kwargs):
        del kwargs
        proposal = AnalysisProposal(
            summary="Synthetic summary",
            entities=["Synthetic Actor"],
            classifications={"stance": "synthetic"},
            formations=["Synthetic Formation"],
            uncertainty=["Needs human review"],
        )
        return model_cls.model_validate(proposal.model_dump()), LLMResponse(
            content=proposal.model_dump_json(), provider="fake", model="fake-model"
        )


def test_model_routing_has_no_silent_cloud_fallback():
    route = resolve_model(machine="laptop", cloud_allowed=False)
    assert route.mode == "local"
    assert route.model == "gemma4:e4b"
    try:
        resolve_model(requested_model="gemma4:31b-cloud", cloud_allowed=False)
    except ValueError:
        pass
    else:
        raise AssertionError("cloud model must require explicit permission")


def test_stable_memory_and_alias_resolution(tmp_path):
    entry = MemoryEntry.create("entity", "Open Source", aliases=["FOSS"], review_state="CANONICAL")
    assert entry.entry_id == stable_id("entity", "Open Source")
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.put(entry)
    assert store.get(entry.entry_id) == entry
    result = resolve("FOSS", store.all())
    assert result.entry_id == entry.entry_id
    assert not result.abstained


def test_pipeline_enriches_same_canonical_record():
    source_url = "https://example.invalid/post/1"
    record = CanonicalRecord(source_url=source_url, content={"text": "Synthetic source text"})
    memory = [MemoryEntry.create("entity", "Synthetic Actor", aliases=["Actor"])]
    result = analyze_record(record, provider=FakeProvider(), memory_entries=memory)
    assert result.source_url == source_url
    assert result.analysis.summary == "Synthetic summary"
    assert result.analysis.entities[0].review_status == "PROVISIONAL"
    assert result.analysis.classifications[0].source_url == source_url
    assert result.analysis.memory_refs == [memory[0].entry_id]
    assert result.analysis.model_runs[0]["provider"] == "fake"
    assert result.provenance[-1].metadata["stage"] == "analysis"


def test_memory_resolution_can_abstain():
    entry = MemoryEntry.create("entity", "Alpha")
    result = resolve("completely unrelated phrase", [entry], threshold=0.95)
    assert result.abstained
    assert result.entry_id is None
