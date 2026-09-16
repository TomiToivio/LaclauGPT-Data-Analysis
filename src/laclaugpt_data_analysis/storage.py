"""Small storage ports for analysis inputs, outputs and caches.

This module deliberately does not turn Data Analysis into the Data Storage
service. It provides adapters at the boundary so the same analysis code can
run on a laptop or against distributed infrastructure.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from .config import Settings

Record = dict[str, Any]


class RecordStore(Protocol):
    def read(self) -> list[Record]: ...
    def write(self, rows: Iterable[Mapping[str, Any]]) -> None: ...


class CsvStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self) -> list[Record]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def write(self, rows: Iterable[Mapping[str, Any]]) -> None:
        values = [dict(row) for row in rows]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not values:
            self.path.write_text("", encoding="utf-8")
            return
        fieldnames = list(dict.fromkeys(key for row in values for key in row))
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(values)


class SqliteStore:
    def __init__(self, path: str | Path, table: str = "analysis_records"):
        self.path = Path(path)
        self.table = table

    def read(self) -> list[Record]:
        if not self.path.exists():
            return []
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    f'SELECT payload FROM "{self.table}" ORDER BY id'
                ).fetchall()
            except sqlite3.OperationalError:
                return []
        return [json.loads(row["payload"]) for row in rows]

    def write(self, rows: Iterable[Mapping[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payloads = [(json.dumps(dict(row), ensure_ascii=False, default=str),) for row in rows]
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                f'CREATE TABLE IF NOT EXISTS "{self.table}" '
                "(id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL)"
            )
            connection.execute(f'DELETE FROM "{self.table}"')
            connection.executemany(
                f'INSERT INTO "{self.table}" (payload) VALUES (?)', payloads
            )
            connection.commit()


class MongoStore:
    def __init__(
        self,
        url: str,
        database: str,
        collection: str,
        project_id: str,
    ):
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise RuntimeError("MongoDB support requires: pip install '.[remote]'") from exc
        self.project_id = project_id
        self.collection = MongoClient(url)[database][collection]
        self.collection.create_index([("project_id", 1)], name="project_id")
        self.collection.create_index([("source_url", 1)], name="source_url")

    def read(self) -> list[Record]:
        return [
            {key: value for key, value in row.items() if key != "_id"}
            for row in self.collection.find({"project_id": self.project_id})
        ]

    def write(self, rows: Iterable[Mapping[str, Any]]) -> None:
        values = []
        for row in rows:
            payload = dict(row)
            payload["project_id"] = self.project_id
            values.append(payload)
        self.collection.delete_many({"project_id": self.project_id})
        if values:
            self.collection.insert_many(values)


class LocalArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def put_text(self, key: str, value: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def get_text(self, key: str) -> str:
        return (self.root / key).read_text(encoding="utf-8")


class S3ArtifactStore:
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region: str | None = None,
        prefix: str = "",
    ):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("S3 support requires: pip install '.[remote]'") from exc
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)

    def _key(self, key: str) -> str:
        clean = key.lstrip("/")
        return f"{self.prefix}/{clean}" if self.prefix else clean

    def put_text(self, key: str, value: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(key),
            Body=value.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )

    def get_text(self, key: str) -> str:
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        return response["Body"].read().decode("utf-8")


class MemoryCache:
    def __init__(self):
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


class RedisCache:
    def __init__(self, url: str, namespace: str):
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Redis support requires: pip install '.[remote]'") from exc
        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.namespace = namespace

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get(self, key: str) -> str | None:
        return self.client.get(self._key(key))

    def set(self, key: str, value: str) -> None:
        self.client.set(self._key(key), value)


def record_store(settings: Settings, name: str = "analysis") -> RecordStore:
    """Create a storage adapter for a named pipeline state.

    Local backends use the name as a file/table stem. Distributed MongoDB uses
    explicit project-scoped collections. ``raw`` is normally written by Data
    Collection, ``processing`` by Data Analysis while work is in flight, and
    ``analyzed`` is the visualization-ready handoff. Legacy ``analysis`` maps to
    ``annotations`` for backwards compatibility.
    """
    if settings.data_backend == "csv":
        return CsvStore(settings.data_dir / f"{name}.csv")
    if settings.data_backend == "sqlite":
        path = settings.database_url.removeprefix("sqlite:///")
        return SqliteStore(path, table=f"{name}_records")
    if settings.data_backend == "mongodb":
        if not settings.mongo_url:
            raise ValueError("LACLAUGPT_MONGO_URL is required for data_backend=mongodb")
        kind = {"analysis": "annotations"}.get(name, name)
        collection = settings.distributed_namespace.mongo_collection(kind)
        return MongoStore(
            settings.mongo_url,
            settings.mongo_database,
            collection=collection,
            project_id=settings.project_id,
        )
    raise ValueError(f"unsupported data backend: {settings.data_backend}")


def artifact_store(settings: Settings):
    if settings.object_backend == "local":
        return LocalArtifactStore(settings.artifact_dir)
    if settings.object_backend == "s3":
        if not settings.s3_bucket:
            raise ValueError("LACLAUGPT_S3_BUCKET is required for object_backend=s3")
        prefix = settings.distributed_namespace.s3_key("analysis").rstrip("/")
        return S3ArtifactStore(
            settings.s3_bucket,
            settings.s3_endpoint_url,
            settings.s3_region,
            prefix=prefix,
        )
    raise ValueError(f"unsupported object backend: {settings.object_backend}")


def cache(settings: Settings):
    if settings.cache_backend == "memory":
        return MemoryCache()
    if settings.cache_backend == "redis":
        if not settings.redis_url:
            raise ValueError("LACLAUGPT_REDIS_URL is required for cache_backend=redis")
        namespace = settings.distributed_namespace.redis_key("cache")
        return RedisCache(settings.redis_url, namespace)
    raise ValueError(f"unsupported cache backend: {settings.cache_backend}")
