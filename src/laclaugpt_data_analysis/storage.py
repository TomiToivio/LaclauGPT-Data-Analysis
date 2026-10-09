"""Small storage ports for analysis inputs, outputs and caches.

The module keeps local CSV/SQLite usable without remote services while allowing MongoDB
as the preferred shared backend. ``auto`` delegates to the compatibility
``data_backend`` setting first, so deployment profiles and all storage consumers agree
on one effective backend. Distributed deployments fail closed rather than silently
falling back to local persistence.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import sqlite3
from collections.abc import Iterable, Mapping
from functools import cache
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
        payloads = [
            (json.dumps(dict(row), ensure_ascii=False, default=str),) for row in rows
        ]
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
        *,
        client: Any | None = None,
    ):
        if client is None:
            try:
                from pymongo import MongoClient
            except ImportError as exc:
                raise RuntimeError(
                    "MongoDB support requires: pip install '.[remote]'"
                ) from exc
            client = MongoClient(url, serverSelectionTimeoutMS=2500)
        self.client = client
        self.project_id = project_id
        self.collection = client[database][collection]
        self.collection.create_index([("project_id", 1)], name="project_id")
        self.collection.create_index([("source_url", 1)], name="source_url")

    def healthcheck(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def read(self) -> list[Record]:
        return [
            {key: value for key, value in row.items() if key != "_id"}
            for row in self.collection.find({"project_id": self.project_id})
        ]

    def write(self, rows: Iterable[Mapping[str, Any]]) -> None:
        """Upsert rows rather than replacing a project collection wholesale.

        This preserves fields owned by Collection when Analysis writes a partial
        enrichment. A full canonical record may still update those fields explicitly.
        """
        for row in rows:
            payload = dict(row)
            payload["project_id"] = self.project_id
            source_url = str(payload.get("source_url") or "")
            if source_url:
                identity = {"project_id": self.project_id, "source_url": source_url}
            else:
                fallback_key = payload.get("id") or hash(
                    json.dumps(payload, sort_keys=True, default=str)
                )
                identity = {
                    "project_id": self.project_id,
                    "_analysis_key": str(fallback_key),
                }
            self.collection.update_one(identity, {"$set": payload}, upsert=True)


class LocalArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def put_text(self, key: str, value: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def get_text(self, key: str) -> str:
        return (self.root / key).read_text(encoding="utf-8")

    def put_bytes(self, key: str, value: bytes) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)

    def get_bytes(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def upload_file(self, key: str, source: str | Path) -> str:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(source).read_bytes())
        return str(target)

    def download_to(self, key: str, target: str | Path) -> Path:
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((self.root / key).read_bytes())
        return destination

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    def delete(self, key: str) -> None:
        path = self.root / key
        if path.exists():
            path.unlink()


def _s3_timeout_env(name: str, default: float) -> float:
    """Read a positive float timeout from the environment, falling back safely.

    A malformed or non-positive value must never disable the bound — a timeout of
    zero would restore the exact indefinite-block failure this guards against, so
    fall back to the default instead of trusting the value.
    """
    raw = os.getenv(f"LACLAUGPT_{name}", "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _s3_connect_timeout_seconds() -> float:
    """Seconds allowed to establish the TCP/TLS connection to the object store."""
    return _s3_timeout_env("S3_CONNECT_TIMEOUT_SECONDS", 10.0)


def _s3_read_timeout_seconds() -> float:
    """Seconds allowed for a single read from the object store before it raises.

    Generous by design: this bounds a *stalled* socket, not a legitimately slow
    upload. It only needs to be far below the cycle's wall-clock ceiling (#332).
    """
    return _s3_timeout_env("S3_READ_TIMEOUT_SECONDS", 60.0)


def _s3_max_attempts() -> int:
    """Bounded retry attempts for a timed-out object-store operation."""
    raw = os.getenv("LACLAUGPT_S3_MAX_ATTEMPTS", "").strip()
    if not raw:
        return 3
    try:
        value = int(raw)
    except ValueError:
        return 3
    return value if value > 0 else 3


class S3ArtifactStore:
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region: str | None = None,
        prefix: str = "",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        signature_version: str = "s3",
        addressing_style: str = "auto",
    ):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("S3 support requires: pip install '.[remote]'") from exc
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        # A read with no deadline does not raise: it WAITS. That is how a single
        # object-store stall held the AI26 cycle lock for six hours while every
        # hourly tick exited "already running" and the queue backed up behind it
        # (issue #332). Bound connect/read and retries so a stalled socket
        # surfaces as a retryable error instead of an indefinite block.
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region or None,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            config=Config(
                signature_version=signature_version,
                s3={"addressing_style": addressing_style},
                connect_timeout=_s3_connect_timeout_seconds(),
                read_timeout=_s3_read_timeout_seconds(),
                retries={
                    "max_attempts": _s3_max_attempts(),
                    "mode": "standard",
                },
            ),
        )

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
        return (
            self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"]
            .read()
            .decode("utf-8")
        )

    def put_bytes(
        self, key: str, value: bytes, *, content_type: str = "application/octet-stream"
    ) -> str:
        object_key = self._key(key)
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=value,
            ContentType=content_type,
        )
        return f"s3://{self.bucket}/{object_key}"

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()

    def upload_file(self, key: str, source: str | Path) -> str:
        object_key = self._key(key)
        self.client.upload_file(str(source), self.bucket, object_key)
        return f"s3://{self.bucket}/{object_key}"

    def download_to(self, key: str, target: str | Path) -> Path:
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, self._key(key), str(destination))
        return destination

    def download_ref(self, ref: str, target: str | Path) -> Path:
        prefix = f"s3://{self.bucket}/"
        if not ref.startswith(prefix):
            raise ValueError("S3 reference does not belong to configured bucket")
        object_key = ref[len(prefix) :]
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, object_key, str(destination))
        return destination

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except self.client.exceptions.ClientError as exc:
            status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))


def _redis_timeout_seconds(name: str, default: float) -> float:
    """Positive float from the environment, or the default.

    Never returns 0: a zero socket timeout would restore the indefinite block that
    held the AI26 cycle lock (issue #332).
    """
    raw = os.getenv(f"LACLAUGPT_{name}", "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def mongo_client(url: str, *, server_selection_timeout_ms: float | None = None):
    """Build a MongoClient with a FINITE server-selection budget.

    pymongo's server-selection timeout bounds how long an operation waits for a
    usable server; without it a lost primary blocks the call indefinitely — the
    same failure shape as the unbounded Redis/S3 reads in #332.
    """
    try:
        from pymongo import MongoClient
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError("pymongo is required: pip install '.[remote]'") from exc

    if server_selection_timeout_ms is not None and server_selection_timeout_ms > 0:
        budget = server_selection_timeout_ms
    else:
        budget = _redis_timeout_seconds("MONGO_SERVER_SELECTION_TIMEOUT_MS", 5000.0)
    return MongoClient(url, serverSelectionTimeoutMS=budget)


def redis_client(
    url: str,
    *,
    decode_responses: bool = True,
    connect_timeout: float | None = None,
    socket_timeout: float | None = None,
):
    """Build a Redis client with FINITE socket timeouts.

    Centralised so every Redis connection in the runtime shares one bound: a
    stalled Redis read previously blocked a worker indefinitely, and the retry
    policy never saw an exception to act on (#332).

    Callers that need a tighter probe budget (preflight) may pass explicit
    overrides; both are validated, so neither can be set to 0 and silently
    reintroduce the indefinite block.
    """
    import redis  # dependency check: raises at call time if redis is not installed

    connect = (
        connect_timeout
        if connect_timeout is not None and connect_timeout > 0
        else _redis_timeout_seconds("REDIS_CONNECT_TIMEOUT_SECONDS", 10.0)
    )
    read = (
        socket_timeout
        if socket_timeout is not None and socket_timeout > 0
        else _redis_timeout_seconds("REDIS_SOCKET_TIMEOUT_SECONDS", 30.0)
    )
    return redis.Redis.from_url(
        url,
        decode_responses=decode_responses,
        socket_connect_timeout=connect,
        socket_timeout=read,
    )


class MemoryCache:
    def __init__(self):
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


class RedisCache:
    def __init__(self, url: str, namespace: str):
        if importlib.util.find_spec("redis") is None:
            raise RuntimeError("Redis support requires: pip install '.[remote]'")
        self.client = redis_client(url)
        self.namespace = namespace

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get(self, key: str) -> str | None:
        return self.client.get(self._key(key))

    def set(self, key: str, value: str) -> None:
        self.client.set(self._key(key), value)


@cache
def _mongodb_reachable(settings: Settings) -> bool:
    """Probe MongoDB once for an immutable settings value during a process lifetime."""
    if not settings.mongo_url:
        return False
    try:
        try:
            from pymongo import MongoClient
        except ImportError:
            return False
        client = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=1500)
        client.admin.command("ping")
        client.close()
        return True
    except Exception:
        return False


def _requested_storage_backend(settings: Settings) -> str:
    """Resolve the explicit selector first; ``auto`` delegates to ``data_backend``."""
    explicit = (settings.storage_backend or "auto").strip().casefold()
    if explicit != "auto":
        return explicit
    legacy = (settings.data_backend or "").strip().casefold()
    return legacy or "auto"


def resolved_storage_backend(settings: Settings) -> str:
    """Return one effective data backend and enforce distributed-storage semantics.

    Precedence is ``storage_backend`` when explicitly set, otherwise ``data_backend``.
    A remaining ``auto`` may probe MongoDB only for local/custom deployments. A
    deployment declaring ``storage=distributed`` must resolve to MongoDB and fails
    closed if MongoDB is missing or unreachable.
    """
    requested = _requested_storage_backend(settings)
    distributed = (settings.storage or "local").strip().casefold() == "distributed"

    if requested == "auto":
        if distributed:
            requested = "mongodb"
        else:
            requested = (
                "mongodb"
                if settings.mongo_url and _mongodb_reachable(settings)
                else "csv"
            )

    if requested == "mongodb":
        if not settings.mongo_url:
            raise ValueError(
                "storage backend mongodb requires LACLAUGPT_MONGODB_URI or "
                "LACLAUGPT_MONGO_URL"
            )
        if not _mongodb_reachable(settings):
            raise ConnectionError("MongoDB is required but unavailable")
        return "mongodb"

    if requested in {"csv", "sqlite"}:
        if distributed:
            raise ValueError(
                "LACLAUGPT_STORAGE=distributed requires a distributed data backend; "
                f"resolved {requested}"
            )
        return requested

    raise ValueError(f"unsupported storage backend: {requested}")


def record_store(settings: Settings, name: str = "analysis") -> RecordStore:
    backend = resolved_storage_backend(settings)
    if backend == "csv":
        return CsvStore(settings.data_dir / f"{name}.csv")
    if backend == "sqlite":
        path = settings.database_url.removeprefix("sqlite:///")
        return SqliteStore(path, table=f"{name}_records")
    kind = {"analysis": "annotations"}.get(name, name)
    return MongoStore(
        settings.mongo_url or "",
        settings.mongo_database,
        collection=settings.distributed_namespace.mongo_collection(kind),
        project_id=settings.project_id,
    )


def artifact_store(settings: Settings):
    if settings.object_backend == "local":
        return LocalArtifactStore(settings.artifact_dir)
    if settings.object_backend == "s3":
        if not settings.s3_bucket:
            raise ValueError("LACLAUGPT_S3_BUCKET is required for object_backend=s3")
        return S3ArtifactStore(
            settings.s3_bucket,
            settings.s3_endpoint_url,
            settings.s3_region,
            prefix=settings.distributed_namespace.s3_key("analysis").rstrip("/"),
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            signature_version=settings.s3_signature_version,
            addressing_style=settings.s3_addressing_style,
        )
    raise ValueError(f"unsupported object backend: {settings.object_backend}")


def cache_store(settings: Settings):
    if settings.cache_backend == "memory":
        return MemoryCache()
    if settings.cache_backend == "redis":
        if not settings.redis_url:
            raise ValueError("LACLAUGPT_REDIS_URL is required for cache_backend=redis")
        return RedisCache(
            settings.redis_url, settings.distributed_namespace.redis_key("cache")
        )
    raise ValueError(f"unsupported cache backend: {settings.cache_backend}")


# Backwards-compatible public name.
cache_backend = cache_store
cache = cache_store
