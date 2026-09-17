from __future__ import annotations

import sys
import types

import pytest

from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.storage import _mongodb_reachable, resolved_storage_backend
from laclaugpt_data_analysis.task_queue import MongoTaskStore, durable_store_from_settings


def test_auto_honours_data_backend_and_distributed_mongodb_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "laclaugpt_data_analysis.storage._mongodb_reachable",
        lambda settings: False,
    )
    settings = Settings(
        storage="distributed",
        storage_backend="auto",
        data_backend="mongodb",
        mongo_url="mongodb://unreachable.invalid",
    )

    with pytest.raises(ConnectionError, match="required but unavailable"):
        resolved_storage_backend(settings)


def test_distributed_mode_rejects_local_backend_without_fallback():
    settings = Settings(
        storage="distributed",
        storage_backend="auto",
        data_backend="csv",
    )

    with pytest.raises(ValueError, match="requires a distributed data backend"):
        resolved_storage_backend(settings)


def test_explicit_storage_backend_still_has_precedence():
    settings = Settings(
        storage="local",
        storage_backend="sqlite",
        data_backend="mongodb",
        mongo_url="mongodb://example.invalid",
    )
    assert resolved_storage_backend(settings) == "sqlite"


def test_durable_task_store_uses_mongo_settings_names(monkeypatch):
    calls = {}

    class FakeCollection:
        def create_index(self, *args, **kwargs):
            return None

    class FakeDatabase:
        def __getitem__(self, name):
            calls.setdefault("collections", []).append(name)
            return FakeCollection()

    class FakeClient:
        def __init__(self, url):
            calls["url"] = url

        def __getitem__(self, name):
            calls["database"] = name
            return FakeDatabase()

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=FakeClient))
    settings = Settings(
        project_id="ai26",
        storage="distributed",
        data_backend="mongodb",
        mongo_url="mongodb://example.invalid",
        mongo_database="analysis-db",
    )

    store = durable_store_from_settings(settings, run_id="run-76")
    assert isinstance(store, MongoTaskStore)
    assert calls["url"] == settings.mongo_url
    assert calls["database"] == settings.mongo_database


def test_mongodb_reachability_probe_is_cached_for_same_settings(monkeypatch):
    calls = 0

    class FakeAdmin:
        def command(self, name):
            nonlocal calls
            assert name == "ping"
            calls += 1
            return {"ok": 1}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.admin = FakeAdmin()

        def close(self):
            return None

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=FakeClient))
    _mongodb_reachable.cache_clear()
    settings = Settings(mongo_url="mongodb://cached.invalid")

    assert _mongodb_reachable(settings) is True
    assert _mongodb_reachable(settings) is True
    assert calls == 1
    _mongodb_reachable.cache_clear()
