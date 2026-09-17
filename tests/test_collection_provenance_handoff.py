from laclaugpt_data_analysis.distributed_worker import MongoCollectionHandoff
from laclaugpt_data_analysis.models import Provenance


COLLECTION_PROVENANCE = {
    "provenance_id": "collection-prov-1",
    "stage": "collection",
    "collector": "laclaugpt-data-collection",
    "collector_version": "0.1.0",
    "captured_at": "2026-09-17T13:10:05.797645+00:00",
    "capture_id": "capture-1",
    "run_id": "ai26-distributed-001",
    "module": "rss-feedparser",
    "module_version": "1.2.3",
    "git_commit": "abc123",
    "visited_url": "https://www.lesswrong.com/feed.xml?view=frontpage",
    "api_url": "https://www.lesswrong.com/posts/example",
    "transformations": ["rss-atom-parse", "map-entry"],
    "metadata": {"existing": "kept"},
}


def test_analysis_provenance_absorbs_collection_specific_fields() -> None:
    provenance = Provenance.model_validate(COLLECTION_PROVENANCE)

    assert provenance.provenance_id == "collection-prov-1"
    assert provenance.method == "rss-feedparser"
    assert provenance.created_at.isoformat() == "2026-09-17T13:10:05.797645+00:00"
    assert provenance.metadata["existing"] == "kept"
    assert provenance.metadata["collector_version"] == "0.1.0"
    assert provenance.metadata["capture_id"] == "capture-1"
    assert provenance.metadata["run_id"] == "ai26-distributed-001"
    assert provenance.metadata["module"] == "rss-feedparser"
    assert provenance.metadata["transformations"] == ["rss-atom-parse", "map-entry"]


class FakeCollection:
    def find_one(self, query):
        assert query == {
            "project_id": "ai26",
            "source_url": "https://example.invalid/post",
        }
        return {
            "_id": "mongo-routing-only",
            "project_id": "ai26",
            "collection_id": "ai26",
            "arena": "ai-discourse",
            "handoff": {"status": "ready"},
            "schema_version": "1.1.0",
            "source_url": "https://example.invalid/post",
            "content": {"text": "Collected source text"},
            "provenance": [COLLECTION_PROVENANCE],
        }


def test_mongo_collection_handoff_resolves_collection_provenance() -> None:
    handoff = MongoCollectionHandoff.__new__(MongoCollectionHandoff)
    handoff.collection = FakeCollection()
    handoff.project_id = "ai26"

    record = handoff.resolve("https://example.invalid/post")

    assert record.source_url == "https://example.invalid/post"
    assert record.content.text == "Collected source text"
    assert len(record.provenance) == 1
    assert record.provenance[0].method == "rss-feedparser"
    assert record.provenance[0].metadata["visited_url"].endswith("feed.xml?view=frontpage")
