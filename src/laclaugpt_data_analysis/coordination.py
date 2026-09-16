"""Optional distributed coordination for LaclauGPT analysis.

Redis coordinates configuration, requests/events and worker state. It is never the
canonical research datastore: configuration snapshots are also written durably to local
files and analysis results remain in the configured durable store.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .distributed import ProjectNamespace


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _revision(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ConfigRevision:
    project_id: str
    module: str
    revision: str
    payload: dict[str, Any]
    created_at: float
    publisher: str

    @classmethod
    def build(
        cls,
        *,
        project_id: str,
        module: str,
        payload: Mapping[str, Any],
        publisher: str,
    ) -> "ConfigRevision":
        clean = dict(payload)
        return cls(
            project_id=project_id,
            module=module,
            revision=_revision(clean),
            payload=clean,
            created_at=time.time(),
            publisher=publisher,
        )

    def validate(self) -> None:
        if not self.project_id or not self.module or not self.revision or not self.publisher:
            raise ValueError("configuration revision is missing routing/provenance fields")
        if self.revision != _revision(self.payload):
            raise ValueError("configuration revision hash does not match payload")


class ConfigStore(Protocol):
    def publish(self, revision: ConfigRevision) -> str: ...
    def current(self, module: str) -> ConfigRevision | None: ...
    def get(self, module: str, revision: str) -> ConfigRevision | None: ...


class FileConfigStore:
    """Durable local configuration history used with or without Redis."""

    def __init__(self, root: str | Path, *, project_id: str):
        self.root = Path(root)
        self.project_id = project_id
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, module: str, revision: str) -> Path:
        return self.root / self.project_id / module / f"{revision}.json"

    def _current_path(self, module: str) -> Path:
        return self.root / self.project_id / module / "current.json"

    def publish(self, revision: ConfigRevision) -> str:
        revision.validate()
        if revision.project_id != self.project_id:
            raise ValueError("configuration project_id does not match store project")
        target = self._path(revision.module, revision.revision)
        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(asdict(revision), ensure_ascii=False, sort_keys=True, indent=2)
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if existing != encoded:
                raise ValueError("immutable configuration revision collision")
        else:
            target.write_text(encoded, encoding="utf-8")
        self._current_path(revision.module).write_text(encoded, encoding="utf-8")
        return revision.revision

    def _load(self, path: Path) -> ConfigRevision | None:
        if not path.exists():
            return None
        revision = ConfigRevision(**json.loads(path.read_text(encoding="utf-8")))
        revision.validate()
        return revision

    def current(self, module: str) -> ConfigRevision | None:
        return self._load(self._current_path(module))

    def get(self, module: str, revision: str) -> ConfigRevision | None:
        return self._load(self._path(module, revision))


class RedisConfigStore:
    """Redis-backed current/revision config with mandatory durable snapshots."""

    def __init__(
        self,
        url: str,
        *,
        namespace: ProjectNamespace,
        snapshots: FileConfigStore,
    ):
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Redis coordination requires: pip install '.[remote]'") from exc
        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.namespace = namespace
        self.snapshots = snapshots

    @staticmethod
    def _encode(revision: ConfigRevision) -> str:
        return json.dumps(asdict(revision), ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _decode(value: str | None) -> ConfigRevision | None:
        if value is None:
            return None
        revision = ConfigRevision(**json.loads(value))
        revision.validate()
        return revision

    def publish(self, revision: ConfigRevision) -> str:
        revision.validate()
        if revision.project_id != self.namespace.project_id:
            raise ValueError("configuration project_id does not match namespace")
        # Snapshot first so a Redis-only write can never become the sole copy.
        self.snapshots.publish(revision)
        encoded = self._encode(revision)
        version_key = self.namespace.settings_key(revision.module, revision.revision)
        current_key = self.namespace.settings_key(revision.module, "current")
        event_stream = self.namespace.stream_key("config-events")
        pipe = self.client.pipeline(transaction=True)
        pipe.set(version_key, encoded, nx=True)
        pipe.set(current_key, encoded)
        pipe.xadd(
            event_stream,
            {
                "project_id": revision.project_id,
                "module": revision.module,
                "revision": revision.revision,
                "publisher": revision.publisher,
                "created_at": str(revision.created_at),
            },
        )
        pipe.execute()
        return revision.revision

    def current(self, module: str) -> ConfigRevision | None:
        value = self._decode(self.client.get(self.namespace.settings_key(module, "current")))
        return value or self.snapshots.current(module)

    def get(self, module: str, revision: str) -> ConfigRevision | None:
        value = self._decode(self.client.get(self.namespace.settings_key(module, revision)))
        return value or self.snapshots.get(module, revision)


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    project_id: str
    run_id: str
    request_id: str
    correlation_id: str
    sender: str
    recipient: str
    message_type: str
    created_at: float
    config_revision: str
    source_record_id: str = ""
    task_id: str = ""
    payload_ref: str = ""
    body: dict[str, Any] | None = None

    @classmethod
    def build(
        cls,
        *,
        project_id: str,
        run_id: str,
        sender: str,
        recipient: str,
        message_type: str,
        config_revision: str,
        correlation_id: str | None = None,
        source_record_id: str = "",
        task_id: str = "",
        payload_ref: str = "",
        body: Mapping[str, Any] | None = None,
    ) -> "MessageEnvelope":
        request_id = str(uuid.uuid4())
        return cls(
            project_id=project_id,
            run_id=run_id,
            request_id=request_id,
            correlation_id=correlation_id or request_id,
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            created_at=time.time(),
            config_revision=config_revision,
            source_record_id=source_record_id,
            task_id=task_id,
            payload_ref=payload_ref,
            body=dict(body) if body is not None else None,
        )

    def validate(self) -> None:
        required = (
            self.project_id,
            self.run_id,
            self.request_id,
            self.correlation_id,
            self.sender,
            self.recipient,
            self.message_type,
            self.config_revision,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("message envelope is missing required routing/provenance fields")
        if self.body is not None and len(_canonical_json(self.body).encode("utf-8")) > 64 * 1024:
            raise ValueError("message body is too large; store research payloads durably and send a reference")

    def to_fields(self) -> dict[str, str]:
        self.validate()
        values = asdict(self)
        body = values.pop("body")
        fields = {key: str(value) for key, value in values.items()}
        fields["body_json"] = _canonical_json(body or {})
        return fields

    @classmethod
    def from_fields(cls, fields: Mapping[str, Any]) -> "MessageEnvelope":
        message = cls(
            project_id=str(fields["project_id"]),
            run_id=str(fields["run_id"]),
            request_id=str(fields["request_id"]),
            correlation_id=str(fields["correlation_id"]),
            sender=str(fields["sender"]),
            recipient=str(fields["recipient"]),
            message_type=str(fields["message_type"]),
            created_at=float(fields["created_at"]),
            config_revision=str(fields["config_revision"]),
            source_record_id=str(fields.get("source_record_id", "")),
            task_id=str(fields.get("task_id", "")),
            payload_ref=str(fields.get("payload_ref", "")),
            body=json.loads(str(fields.get("body_json", "{}"))) or None,
        )
        message.validate()
        return message


class MessageBus(Protocol):
    def publish(self, message: MessageEnvelope) -> str: ...
    def receive(self, *, block_ms: int = 1000) -> tuple[str, MessageEnvelope] | None: ...
    def ack(self, message_id: str) -> None: ...


class RedisMessageBus:
    """Reliable Redis Streams transport for RAG/agent/human-pipeline messages."""

    def __init__(
        self,
        url: str,
        *,
        namespace: ProjectNamespace,
        service: str,
        consumer: str,
    ):
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Redis coordination requires: pip install '.[remote]'") from exc
        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.stream = namespace.stream_key(f"messages:{service}")
        self.group = f"{service}-consumers"
        self.consumer = consumer
        try:
            self.client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def publish(self, message: MessageEnvelope) -> str:
        return str(self.client.xadd(self.stream, message.to_fields()))

    def receive(self, *, block_ms: int = 1000) -> tuple[str, MessageEnvelope] | None:
        response = self.client.xreadgroup(
            self.group, self.consumer, {self.stream: ">"}, count=1, block=block_ms
        )
        if not response:
            return None
        _, messages = response[0]
        message_id, fields = messages[0]
        return str(message_id), MessageEnvelope.from_fields(fields)

    def ack(self, message_id: str) -> None:
        self.client.xack(self.stream, self.group, message_id)


class InMemoryMessageBus:
    """Offline/test bus with the same envelope contract as Redis Streams."""

    def __init__(self):
        self.ready: list[tuple[str, MessageEnvelope]] = []
        self.pending: dict[str, MessageEnvelope] = {}
        self._sequence = 0

    def publish(self, message: MessageEnvelope) -> str:
        message.validate()
        self._sequence += 1
        message_id = str(self._sequence)
        self.ready.append((message_id, message))
        return message_id

    def receive(self, *, block_ms: int = 1000) -> tuple[str, MessageEnvelope] | None:
        del block_ms
        if not self.ready:
            return None
        message_id, message = self.ready.pop(0)
        self.pending[message_id] = message
        return message_id, message

    def ack(self, message_id: str) -> None:
        self.pending.pop(message_id, None)


def config_store_from_settings(settings: Any) -> ConfigStore:
    """Use Redis when configured; otherwise retain durable local-only semantics."""
    snapshots = FileConfigStore(settings.data_path("config", "snapshots"), project_id=settings.project_id)
    if not settings.redis_url:
        return snapshots
    return RedisConfigStore(
        settings.redis_url,
        namespace=settings.distributed_namespace,
        snapshots=snapshots,
    )
