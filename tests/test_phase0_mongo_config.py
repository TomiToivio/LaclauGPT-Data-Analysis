import laclaugpt_mongo


class FakeDatabase:
    def __getitem__(self, name):
        return ("collection", name)


class FakeClient:
    def __init__(self, uri):
        self.uri = uri

    def __getitem__(self, name):
        assert name == "laclaugpt"
        return FakeDatabase()


def test_collection_accepts_collection_style_env(monkeypatch):
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("MONGO_DB_NAME", raising=False)
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://example.invalid")
    monkeypatch.setenv("LACLAUGPT_MONGODB_DATABASE", "laclaugpt")
    monkeypatch.setattr(laclaugpt_mongo, "MongoClient", FakeClient)

    collection = laclaugpt_mongo._collection("ai26")

    assert collection == ("collection", "laclaugpt2_ai26_scraper_collection")


def test_legacy_env_names_still_work(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://legacy.invalid")
    monkeypatch.setenv("MONGO_DB_NAME", "laclaugpt")
    monkeypatch.delenv("LACLAUGPT_MONGODB_URI", raising=False)
    monkeypatch.delenv("LACLAUGPT_MONGODB_DATABASE", raising=False)
    monkeypatch.setattr(laclaugpt_mongo, "MongoClient", FakeClient)

    collection = laclaugpt_mongo._collection("ai26")

    assert collection == ("collection", "laclaugpt2_ai26_scraper_collection")
