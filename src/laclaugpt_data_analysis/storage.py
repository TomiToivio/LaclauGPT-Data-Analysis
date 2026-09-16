"""Small storage ports for analysis inputs, outputs and caches.

The module keeps local CSV/SQLite usable without remote services while allowing MongoDB
as the preferred shared backend. ``auto`` only uses MongoDB when a URI is explicitly
configured *and* reachable; it never silently invents or discovers a remote endpoint.
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
    def __init__(self, path: str | Path): self.path = Path(path)
    def read(self) -> list[Record]:
        if not self.path.exists(): return []
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    def write(self, rows: Iterable[Mapping[str, Any]]) -> None:
        values = [dict(row) for row in rows]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not values:
            self.path.write_text("", encoding="utf-8"); return
        fieldnames = list(dict.fromkeys(key for row in values for key in row))
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames); writer.writeheader(); writer.writerows(values)


class SqliteStore:
    def __init__(self, path: str | Path, table: str = "analysis_records"):
        self.path, self.table = Path(path), table
    def read(self) -> list[Record]:
        if not self.path.exists(): return []
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            try: rows = connection.execute(f'SELECT payload FROM "{self.table}" ORDER BY id').fetchall()
            except sqlite3.OperationalError: return []
        return [json.loads(row["payload"]) for row in rows]
    def write(self, rows: Iterable[Mapping[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payloads = [(json.dumps(dict(row), ensure_ascii=False, default=str),) for row in rows]
        with sqlite3.connect(self.path) as connection:
            connection.execute(f'CREATE TABLE IF NOT EXISTS "{self.table}" (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL)')
            connection.execute(f'DELETE FROM "{self.table}"')
            connection.executemany(f'INSERT INTO "{self.table}" (payload) VALUES (?)', payloads); connection.commit()


class MongoStore:
    def __init__(self, url: str, database: str, collection: str, project_id: str, *, client: Any | None = None):
        if client is None:
            try: from pymongo import MongoClient
            except ImportError as exc: raise RuntimeError("MongoDB support requires: pip install '.[remote]'") from exc
            client = MongoClient(url, serverSelectionTimeoutMS=2500)
        self.client, self.project_id = client, project_id
        self.collection = client[database][collection]
        self.collection.create_index([("project_id", 1)], name="project_id")
        self.collection.create_index([("source_url", 1)], name="source_url")
    def healthcheck(self) -> bool:
        try: self.client.admin.command("ping"); return True
        except Exception: return False
    def read(self) -> list[Record]:
        return [{key: value for key, value in row.items() if key != "_id"} for row in self.collection.find({"project_id": self.project_id})]
    def write(self, rows: Iterable[Mapping[str, Any]]) -> None:
        """Upsert rows rather than replacing a project collection wholesale.

        This preserves fields owned by Collection when Analysis writes a partial
        enrichment. A full canonical record may still update those fields explicitly.
        """
        for row in rows:
            payload = dict(row); payload["project_id"] = self.project_id
            source_url = str(payload.get("source_url") or "")
            identity = {"project_id": self.project_id, "source_url": source_url} if source_url else {"project_id": self.project_id, "_analysis_key": str(payload.get("id") or hash(json.dumps(payload, sort_keys=True, default=str)))}
            self.collection.update_one(identity, {"$set": payload}, upsert=True)


class LocalArtifactStore:
    def __init__(self, root: str | Path): self.root = Path(root)
    def put_text(self, key: str, value: str) -> None:
        path = self.root / key; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(value, encoding="utf-8")
    def get_text(self, key: str) -> str: return (self.root / key).read_text(encoding="utf-8")


class S3ArtifactStore:
    def __init__(self, bucket: str, endpoint_url: str | None = None, region: str | None = None, prefix: str = ""):
        try: import boto3
        except ImportError as exc: raise RuntimeError("S3 support requires: pip install '.[remote]'") from exc
        self.bucket, self.prefix = bucket, prefix.rstrip("/")
        self.client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)
    def _key(self, key: str) -> str:
        clean = key.lstrip("/"); return f"{self.prefix}/{clean}" if self.prefix else clean
    def put_text(self, key: str, value: str) -> None: self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=value.encode("utf-8"), ContentType="text/plain; charset=utf-8")
    def get_text(self, key: str) -> str: return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read().decode("utf-8")


class MemoryCache:
    def __init__(self): self.values: dict[str, str] = {}
    def get(self, key: str) -> str | None: return self.values.get(key)
    def set(self, key: str, value: str) -> None: self.values[key] = value


class RedisCache:
    def __init__(self, url: str, namespace: str):
        try: import redis
        except ImportError as exc: raise RuntimeError("Redis support requires: pip install '.[remote]'") from exc
        self.client, self.namespace = redis.Redis.from_url(url, decode_responses=True), namespace
    def _key(self, key: str) -> str: return f"{self.namespace}:{key}"
    def get(self, key: str) -> str | None: return self.client.get(self._key(key))
    def set(self, key: str, value: str) -> None: self.client.set(self._key(key), value)


def _mongodb_reachable(settings: Settings) -> bool:
    if not settings.mongo_url: return False
    try:
        try: from pymongo import MongoClient
        except ImportError: return False
        client = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=1500)
        client.admin.command("ping"); client.close(); return True
    except Exception:
        return False


def resolved_storage_backend(settings: Settings) -> str:
    """Resolve ``auto|mongodb|csv|sqlite`` without silently using remote services."""
    requested = (settings.storage_backend or settings.data_backend or "csv").casefold()
    if requested == "auto":
        return "mongodb" if settings.mongo_url and _mongodb_reachable(settings) else "csv"
    if requested == "mongodb":
        if not settings.mongo_url: raise ValueError("storage_backend=mongodb requires a configured MongoDB URI")
        if not _mongodb_reachable(settings): raise ConnectionError("MongoDB is required but unavailable")
        return "mongodb"
    if requested in {"csv", "sqlite"}: return requested
    raise ValueError(f"unsupported storage backend: {requested}")


def record_store(settings: Settings, name: str = "analysis") -> RecordStore:
    backend = resolved_storage_backend(settings)
    if backend == "csv": return CsvStore(settings.data_dir / f"{name}.csv")
    if backend == "sqlite":
        path = settings.database_url.removeprefix("sqlite:///"); return SqliteStore(path, table=f"{name}_records")
    kind = {"analysis": "annotations"}.get(name, name)
    return MongoStore(settings.mongo_url or "", settings.mongo_database, collection=settings.distributed_namespace.mongo_collection(kind), project_id=settings.project_id)


def artifact_store(settings: Settings):
    if settings.object_backend == "local": return LocalArtifactStore(settings.artifact_dir)
    if settings.object_backend == "s3":
        if not settings.s3_bucket: raise ValueError("LACLAUGPT_S3_BUCKET is required for object_backend=s3")
        return S3ArtifactStore(settings.s3_bucket, settings.s3_endpoint_url, settings.s3_region, prefix=settings.distributed_namespace.s3_key("analysis").rstrip("/"))
    raise ValueError(f"unsupported object backend: {settings.object_backend}")


def cache(settings: Settings):
    if settings.cache_backend == "memory": return MemoryCache()
    if settings.cache_backend == "redis":
        if not settings.redis_url: raise ValueError("LACLAUGPT_REDIS_URL is required for cache_backend=redis")
        return RedisCache(settings.redis_url, settings.distributed_namespace.redis_key("cache"))
    raise ValueError(f"unsupported cache backend: {settings.cache_backend}")
