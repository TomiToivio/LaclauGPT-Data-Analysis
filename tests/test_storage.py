from laclaugpt_data_analysis.storage import CsvStore, LocalArtifactStore, MemoryCache, SqliteStore


def test_csv_roundtrip(tmp_path):
    store = CsvStore(tmp_path / "rows.csv")
    rows = [{"id": "1", "text": "hello"}, {"id": "2", "text": "world"}]
    store.write(rows)
    assert store.read() == rows


def test_sqlite_roundtrip(tmp_path):
    store = SqliteStore(tmp_path / "rows.sqlite3")
    rows = [{"id": 1, "label": "accel"}, {"id": 2, "label": "critical"}]
    store.write(rows)
    assert store.read() == rows


def test_local_artifact_store(tmp_path):
    store = LocalArtifactStore(tmp_path)
    store.put_text("reports/example.txt", "analysis")
    assert store.get_text("reports/example.txt") == "analysis"


def test_memory_cache():
    cache = MemoryCache()
    assert cache.get("missing") is None
    cache.set("key", "value")
    assert cache.get("key") == "value"
