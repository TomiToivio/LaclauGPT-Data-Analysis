"""Phase 0 MongoDB environment contract (issue #192).

Phase 0 runs Collection and Analysis from one cron/CLI environment, so every Phase 0
entry point must accept the same MongoDB configuration names. Collection's Settings
use the ``LACLAUGPT_`` namespace; the legacy Phase 0 core used bare ``MONGO_`` names.
Both must work, and neither may require the other's aliases to be exported.
"""
from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "laclaugpt"))

import laclaugpt_mongo  # noqa: E402
from laclaugpt_mongo import (  # noqa: E402
    MONGO_DB_ENV_VARS,
    MONGO_URI_ENV_VARS,
    resolve_mongo_config,
)

ALL_ENV_VARS = (*MONGO_URI_ENV_VARS, *MONGO_DB_ENV_VARS)


class FakeDatabase:
    def __init__(self, name: str) -> None:
        self.name = name

    def __getitem__(self, name):
        return ("collection", name)


class FakeClient:
    def __init__(self, uri, **_kwargs) -> None:
        self.uri = uri

    def __getitem__(self, name):
        assert name == "laclaugpt"
        return FakeDatabase(name)


@pytest.fixture(autouse=True)
def _clear_mongo_env(monkeypatch):
    """Start every test from an environment with no MongoDB names set."""
    for name in ALL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(laclaugpt_mongo, "MongoClient", FakeClient, raising=False)
    yield


# --------------------------------------------------------------------------
# The shared resolver
# --------------------------------------------------------------------------

def test_collection_style_names_resolve(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://collection.invalid")
    monkeypatch.setenv("LACLAUGPT_MONGODB_DATABASE", "laclaugpt")
    assert resolve_mongo_config() == ("mongodb://collection.invalid", "laclaugpt")


def test_legacy_names_still_resolve(monkeypatch) -> None:
    monkeypatch.setenv("MONGO_URI", "mongodb://legacy.invalid")
    monkeypatch.setenv("MONGO_DB_NAME", "laclaugpt")
    assert resolve_mongo_config() == ("mongodb://legacy.invalid", "laclaugpt")


def test_legacy_names_win_when_both_are_set(monkeypatch) -> None:
    """Backward compatibility: an existing deployment keeps its precedence."""
    monkeypatch.setenv("MONGO_URI", "mongodb://legacy.invalid")
    monkeypatch.setenv("MONGO_DB_NAME", "legacy_db")
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://collection.invalid")
    monkeypatch.setenv("LACLAUGPT_MONGODB_DATABASE", "collection_db")
    assert resolve_mongo_config() == ("mongodb://legacy.invalid", "legacy_db")


def test_missing_configuration_names_both_accepted_pairs(monkeypatch) -> None:
    """A misconfigured cron job must say what to set."""
    with pytest.raises(RuntimeError) as excinfo:
        resolve_mongo_config()
    message = str(excinfo.value)
    for name in ALL_ENV_VARS:
        assert name in message, f"{name} must be named in the error"


def test_partial_configuration_is_rejected(monkeypatch) -> None:
    """URI without a database is a configuration error, not a silent default."""
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://example.invalid")
    with pytest.raises(RuntimeError):
        resolve_mongo_config()


# --------------------------------------------------------------------------
# Every Phase 0 entry point must honour it
# --------------------------------------------------------------------------

def test_collection_helper_uses_the_shared_contract(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://example.invalid")
    monkeypatch.setenv("LACLAUGPT_MONGODB_DATABASE", "laclaugpt")
    collection = laclaugpt_mongo._collection("ai26")
    assert collection == ("collection", "laclaugpt2_ai26_scraper_collection")


def test_collection_helper_uses_legacy_names(monkeypatch) -> None:
    monkeypatch.setenv("MONGO_URI", "mongodb://example.invalid")
    monkeypatch.setenv("MONGO_DB_NAME", "laclaugpt")
    collection = laclaugpt_mongo._collection("ai26")
    assert collection == ("collection", "laclaugpt2_ai26_scraper_collection")


def test_seed_graph_entry_point_accepts_collection_style_names(monkeypatch) -> None:
    """The graph-seeding CLI is a Phase 0 entry point too (issue #179)."""
    module = importlib.import_module("laclaugpt_seed_graph")
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://example.invalid")
    monkeypatch.setenv("LACLAUGPT_MONGODB_DATABASE", "laclaugpt")
    monkeypatch.setattr(module, "MongoClient", FakeClient)
    assert module._db() is not None


def test_seed_graph_entry_point_still_accepts_legacy_names(monkeypatch) -> None:
    module = importlib.import_module("laclaugpt_seed_graph")
    monkeypatch.setenv("MONGO_URI", "mongodb://example.invalid")
    monkeypatch.setenv("MONGO_DB_NAME", "laclaugpt")
    monkeypatch.setattr(module, "MongoClient", FakeClient)
    assert module._db() is not None


def test_no_phase0_module_requires_legacy_names_only() -> None:
    """Guard: no Phase 0 entry point may depend on the legacy names alone.

    This is the defect #192 describes — a module that only knows ``MONGO_URI`` cannot
    be configured from one shared cron environment. The check inspects actual
    expressions, not prose, so a docstring that merely mentions the new names cannot
    satisfy it.
    """
    laclaugpt_dir = Path(__file__).resolve().parents[1] / "laclaugpt"
    offenders: list[str] = []
    for path in sorted(laclaugpt_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        legacy = False
        shared = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr != "getenv" or not node.args:
                    continue
                argument = node.args[0]
                if not isinstance(argument, ast.Constant):
                    continue
                if argument.value == "MONGO_URI":
                    legacy = True
                elif argument.value in {"LACLAUGPT_MONGODB_URI", "LACLAUGPT_MONGODB_DATABASE"}:
                    shared = True
            # Accept delegation to the shared resolver instead of a direct read.
            if isinstance(node, ast.ImportFrom) and node.module == "laclaugpt_mongo":
                if any(alias.name == "resolve_mongo_config" for alias in node.names):
                    shared = True
        if legacy and not shared:
            offenders.append(path.name)
    assert not offenders, f"legacy-only MongoDB configuration in {offenders}"
