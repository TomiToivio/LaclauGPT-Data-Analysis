"""Fake Redis/MongoDB for offline distributed-coordination tests."""
from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any


class FakeRedis:
    """Enough SET NX EX / GET / DEL / XADD / EXPIRE for coordination tests."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}
        self._streams: dict[str, list[dict[str, str]]] = {}

    def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        if nx and name in self._store:
            stored_value, expiry = self._store[name]
            if expiry is None or expiry > time.monotonic():
                return False
        self._store[name] = (value, time.monotonic() + ex if ex else None)
        return True

    def get(self, name: str) -> str | None:
        entry = self._store.get(name)
        if entry is None:
            return None
        value, expiry = entry
        if expiry is not None and expiry <= time.monotonic():
            del self._store[name]
            return None
        return value

    def delete(self, *names: str) -> int:
        deleted = 0
        for name in names:
            if name in self._store:
                del self._store[name]
                deleted += 1
        return deleted

    def expire(self, name: str, seconds: int) -> bool:
        entry = self._store.get(name)
        if entry is None:
            return False
        self._store[name] = (entry[0], time.monotonic() + seconds)
        return True

    def xadd(
        self, name: str, fields: dict[str, str], maxlen: int | None = None, approximate: bool = True
    ) -> str:
        self._streams.setdefault(name, []).append(dict(fields))
        return f"{len(self._streams[name])}-1"

    def stream(self, name: str) -> list[dict[str, str]]:
        return list(self._streams.get(name, []))


class FakeCollection:
    """Minimal find_one/update_one/replace_one/count_documents over dicts."""

    def __init__(self, documents: Iterable[dict[str, Any]] | None = None) -> None:
        self._docs: dict[str, dict[str, Any]] = {}
        self._counter = 0
        for doc in documents or []:
            self._insert(doc)

    def _insert(self, doc: dict[str, Any]) -> str:
        self._counter += 1
        key = str(doc.get("_id") or f"oid-{self._counter}")
        stored = dict(doc)
        stored.setdefault("_id", key)
        self._docs[key] = stored
        return key

    @staticmethod
    def _matches(doc: dict[str, Any], flt: dict[str, Any]) -> bool:
        for key, condition in flt.items():
            if key == "_id":
                if doc.get("_id") != condition:
                    return False
                continue
            value = doc.get(key)
            if isinstance(condition, dict):
                if "$in" in condition:
                    if value not in condition["$in"]:
                        return False
                elif "$gte" in condition:
                    if not (isinstance(value, (int, float)) and value >= condition["$gte"]):
                        return False
                elif "$lte" in condition:
                    if not (isinstance(value, (int, float)) and value <= condition["$lte"]):
                        return False
                else:
                    if value != condition:
                        return False
            else:
                if value != condition:
                    return False
        return True

    def find_one(
        self, flt: dict[str, Any], projection: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        for doc in self._docs.values():
            if self._matches(doc, flt):
                if projection and projection.get("_id") == 0:
                    return {k: v for k, v in doc.items() if k != "_id"}
                return dict(doc)
        return None

    def update_one(self, flt: dict[str, Any], update: dict[str, Any], upsert: bool = False) -> Any:
        for doc in self._docs.values():
            if self._matches(doc, flt):
                doc.update(update.get("$set", {}))
                if "$inc" in update:
                    for key, amount in update["$inc"].items():
                        doc[key] = doc.get(key, 0) + amount
                return _Result(matched=1)
        if upsert:
            new_doc = dict(flt)
            new_doc.update(update.get("$set", {}))
            self._insert(new_doc)
            return _Result(matched=0)
        return _Result(matched=0)

    def replace_one(self, flt: dict[str, Any], replacement: dict[str, Any], upsert: bool = False) -> Any:
        replacement = dict(replacement)
        for key, doc in self._docs.items():
            if self._matches(doc, flt):
                replacement["_id"] = doc["_id"]
                self._docs[key] = replacement
                return _Result(matched=1)
        if upsert:
            self._insert(replacement)
            return _Result(matched=0)
        return _Result(matched=0)

    def count_documents(self, flt: dict[str, Any]) -> int:
        return sum(1 for doc in self._docs.values() if self._matches(doc, flt))

    def all(self) -> list[dict[str, Any]]:
        return list(self._docs.values())


class _Result:
    def __init__(self, matched: int) -> None:
        self.matched_count = matched