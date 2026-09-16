"""AI26 distributed worker built on the generic task-queue contract.

Redis is coordination only, MongoDB owns durable canonical/result state, and the
existing canonical pipeline performs analysis. Private configuration and codebooks are
verified against a frozen run manifest before any task is processed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .canonical import SCHEMA_VERSION, CanonicalRecord
from .canonical_pipeline import PipelineContext, run_canonical_pipeline
from .codebooks import load_codebook
from .config import Settings, load_settings
from .llm.ollama import OllamaProvider
from .task_queue import (
    TaskEnvelope,
    TaskQueue,
    TaskWorker,
    durable_store_from_settings,
    redis_queue_from_settings,
)

AI26_MODEL = "gemma4:12b"
AI26_NOT_BEFORE = "2026-09-01T00:00:00+00:00"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, path: Path) -> Path:
    root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"private runtime file must be inside {root}") from exc
    if not resolved.is_file():
        raise ValueError(f"private runtime file does not exist: {resolved}")
    return resolved


def _runtime_public_git_sha() -> str:
    """Resolve the checked-out public code revision without leaking repository data."""
    explicit = os.environ.get("LACLAUGPT_PUBLIC_GIT_SHA", "").strip()
    if explicit:
        return explicit
    repo_root = Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(
            "cannot determine public Git SHA; set LACLAUGPT_PUBLIC_GIT_SHA explicitly"
        ) from exc
    sha = completed.stdout.strip()
    if not sha:
        raise ValueError("cannot determine public Git SHA")
    return sha


def collection_records_name(settings: Settings) -> str:
    """Collection's published Mongo handoff lives in the project ``records`` collection."""
    return settings.distributed_namespace.mongo_collection("records")


@dataclass(frozen=True, slots=True)
class FrozenRunManifest:
    project_id: str
    run_id: str
    schema_version: str
    config_sha256: str
    codebook_sha256: str
    model: str
    public_git_sha: str

    @classmethod
    def load(cls, path: str | Path) -> FrozenRunManifest:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class WorkerBinding:
    manifest: FrozenRunManifest
    manifest_path: Path
    private_config: Path
    codebook: Path
    worker_id: str

    @classmethod
    def build(
        cls,
        *,
        manifest_path: str | Path,
        private_root: str | Path,
        private_config: str | Path,
        codebook: str | Path,
        worker_id: str | None = None,
    ) -> WorkerBinding:
        root = Path(private_root)
        if not root.exists() or not root.is_dir():
            raise ValueError("LACLAUGPT_PRIVATE_CONFIG_DIR must name an existing directory")
        manifest_file = _inside(root, Path(manifest_path))
        config_path = _inside(root, Path(private_config))
        codebook_path = _inside(root, Path(codebook))
        manifest = FrozenRunManifest.load(manifest_file)
        binding = cls(
            manifest=manifest,
            manifest_path=manifest_file,
            private_config=config_path,
            codebook=codebook_path,
            worker_id=worker_id or f"{socket.gethostname()}-{os.getpid()}",
        )
        binding.validate_files()
        return binding

    def validate_files(self) -> None:
        manifest = self.manifest
        if manifest.project_id != "ai26":
            raise ValueError("AI26 integration worker requires project_id=ai26")
        if manifest.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"schema mismatch: manifest={manifest.schema_version} runtime={SCHEMA_VERSION}"
            )
        if manifest.model != AI26_MODEL:
            raise ValueError(f"AI26 distributed test requires model {AI26_MODEL}")
        if _sha256(self.private_config) != manifest.config_sha256:
            raise ValueError("private config hash does not match frozen run manifest")
        if _sha256(self.codebook) != manifest.codebook_sha256:
            raise ValueError("codebook hash does not match frozen run manifest")

    def validate_runtime_code(self) -> None:
        runtime_sha = _runtime_public_git_sha()
        if runtime_sha != self.manifest.public_git_sha:
            raise ValueError(
                "public Git SHA does not match frozen run manifest: "
                f"manifest={self.manifest.public_git_sha} runtime={runtime_sha}"
            )

    def validate_task(self, task: TaskEnvelope) -> None:
        manifest = self.manifest
        checks = {
            "project_id": (task.project_id, manifest.project_id),
            "run_id": (task.run_id, manifest.run_id),
            "schema_version": (task.schema_version, manifest.schema_version),
            "config_revision": (task.config_revision, manifest.config_sha256),
            "codebook_revision": (task.codebook_revision, manifest.codebook_sha256),
        }
        mismatches = [name for name, pair in checks.items() if pair[0] != pair[1]]
        if mismatches:
            raise ValueError("task/run manifest mismatch: " + ", ".join(mismatches))
        if task.task_type != "analyze-record":
            raise ValueError(f"unsupported task type: {task.task_type}")

    def task_from_handoff(self, handoff: dict[str, Any]) -> TaskEnvelope:
        """Translate Collection's durable handoff envelope into a reference-only task."""
        if str(handoff.get("status") or "") != "ready":
            raise ValueError("only ready Collection handoffs may be queued")
        source_url = str(handoff.get("source_url") or "")
        handoff_key = str(handoff.get("handoff_key") or "")
        run_id = str(handoff.get("run_id") or "")
        if run_id != self.manifest.run_id:
            raise ValueError("Collection handoff run does not match frozen run manifest")
        task = TaskEnvelope(
            task_id=f"analysis:{handoff_key}",
            idempotency_key=handoff_key,
            project_id=self.manifest.project_id,
            run_id=self.manifest.run_id,
            task_type="analyze-record",
            record_ref=source_url,
            schema_version=self.manifest.schema_version,
            config_revision=self.manifest.config_sha256,
            codebook_revision=self.manifest.codebook_sha256,
        )
        task.validate()
        return task

    def provenance(self) -> dict[str, str]:
        manifest = self.manifest
        return {
            "run_id": manifest.run_id,
            "worker_id": self.worker_id,
            "model": manifest.model,
            "public_git_sha": manifest.public_git_sha,
            "schema_version": manifest.schema_version,
            "config_sha256": manifest.config_sha256,
            "codebook_sha256": manifest.codebook_sha256,
        }


def enforce_local_model(manifest: FrozenRunManifest) -> None:
    if manifest.model != AI26_MODEL:
        raise ValueError(f"AI26 distributed test requires model {AI26_MODEL}")
    mode = os.environ.get("LLM_MODE", "local").strip().lower()
    if mode not in {"", "local"}:
        raise ValueError("AI26 distributed test forbids cloud/external Ollama mode")
    fallback = os.environ.get("LLM_ALLOW_CLOUD_FALLBACK", "").strip().casefold()
    if fallback in {"1", "true", "yes", "on"}:
        raise ValueError("AI26 distributed test forbids cloud fallback")
    configured_model = (
        os.environ.get("LACLAUGPT_OLLAMA_MODEL")
        or os.environ.get("OLLAMA_MODEL")
        or AI26_MODEL
    )
    if configured_model != AI26_MODEL:
        raise ValueError(f"configured Ollama model must be {AI26_MODEL}")
    os.environ["LLM_MODE"] = "local"
    os.environ["LLM_ALLOW_CLOUD_FALLBACK"] = "0"
    os.environ["LACLAUGPT_OLLAMA_MODEL"] = AI26_MODEL


class MongoCollectionHandoff:
    """Read Collection's durable canonical records and ready handoff envelopes."""

    def __init__(self, settings: Settings):
        if not settings.mongo_url:
            raise ValueError("MongoDB is required for the AI26 distributed worker")
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise RuntimeError("MongoDB worker support requires: pip install '.[remote]'") from exc
        self.collection = MongoClient(settings.mongo_url)[settings.mongo_database][
            collection_records_name(settings)
        ]
        self.project_id = settings.project_id

    def resolve(self, source_url: str) -> CanonicalRecord:
        row = self.collection.find_one({"project_id": self.project_id, "source_url": source_url})
        if row is None:
            raise KeyError(f"canonical source not found: {source_url}")
        clean = {key: value for key, value in row.items() if key in CanonicalRecord.model_fields}
        return CanonicalRecord.model_validate(clean)

    def ready_handoffs(self, run_id: str, *, limit: int) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        cursor = self.collection.find(
            {
                "project_id": self.project_id,
                "handoff.status": "ready",
                "handoff.run_id": run_id,
                "handoff.published_at": {"$gte": AI26_NOT_BEFORE},
            },
            {"handoff": 1, "_id": 0},
        ).sort(
            [
                ("handoff.source_priority", 1),
                ("handoff.published_at", -1),
                ("source_url", 1),
            ]
        ).limit(limit)
        return [dict(row.get("handoff") or {}) for row in cursor]


class AI26Handler:
    def __init__(self, binding: WorkerBinding, settings: Settings, handoff: MongoCollectionHandoff):
        self.binding = binding
        self.settings = settings
        self.handoff = handoff
        self.codebook = load_codebook(binding.codebook)
        self.provider = OllamaProvider(host=os.environ.get("OLLAMA_HOST") or None)

    def __call__(self, task: TaskEnvelope) -> dict[str, Any]:
        record = self.handoff.resolve(task.record_ref)
        context = PipelineContext(
            project_context="AI26 distributed bounded test",
            provenance={
                "private_config_sha256": [self.binding.manifest.config_sha256],
                "codebook_sha256": [self.binding.manifest.codebook_sha256],
            },
        )
        analyzed = run_canonical_pipeline(
            record,
            provider=self.provider,
            context=context,
            codebook_entries=self.codebook.entries,
            model=AI26_MODEL,
            project_profile="ai26",
            allow_cloud_fallback=False,
        )
        return analyzed.model_dump(mode="json")


class AI26TaskWorker(TaskWorker):
    """Task worker with explicit retry requeue so attempt counters actually advance."""

    def run_once(self, *, reclaim_idle_ms: int | None = None) -> str:
        claimed = None
        if reclaim_idle_ms is not None:
            claimed = self.queue.reclaim(min_idle_ms=reclaim_idle_ms)
        if claimed is None:
            claimed = self.queue.claim()
        if claimed is None:
            return "idle"

        task = claimed.task
        if self.validator is not None:
            self.validator(task)

        if self.durable_store.has_result(task.idempotency_key):
            self.queue.ack(claimed.message_id)
            return "duplicate"

        try:
            result = self.handler(task)
            inserted = self.durable_store.write_result(
                task.idempotency_key,
                result,
                self.provenance,
            )
            self.queue.ack(claimed.message_id)
            return "completed" if inserted else "duplicate"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.durable_store.write_failure(task, error, self.provenance)
            if task.attempt >= self.max_attempts:
                self.queue.dead_letter(task, error)
                self.queue.ack(claimed.message_id)
                return "dead-letter"

            retry_task = replace(task, attempt=task.attempt + 1)
            retry_task.validate()
            self.queue.publish(retry_task)
            self.queue.ack(claimed.message_id)
            return "retry"


def seed_ready_tasks(
    binding: WorkerBinding,
    handoff: MongoCollectionHandoff,
    queue: TaskQueue,
    *,
    limit: int,
) -> int:
    """Boundedly mirror durable Collection-ready handoffs into the worker task stream."""
    count = 0
    for envelope in handoff.ready_handoffs(binding.manifest.run_id, limit=limit):
        queue.publish(binding.task_from_handoff(envelope))
        count += 1
    return count


def build_worker(binding: WorkerBinding, settings: Settings) -> tuple[TaskWorker, MongoCollectionHandoff]:
    binding.validate_runtime_code()
    enforce_local_model(binding.manifest)
    if settings.project_id != binding.manifest.project_id:
        raise ValueError("settings project_id does not match frozen run manifest")
    queue = redis_queue_from_settings(
        settings,
        run_id=binding.manifest.run_id,
        worker_id=binding.worker_id,
    )
    durable = durable_store_from_settings(settings, run_id=binding.manifest.run_id)
    handoff = MongoCollectionHandoff(settings)
    worker = AI26TaskWorker(
        queue=queue,
        durable_store=durable,
        handler=AI26Handler(binding, settings, handoff),
        worker_id=binding.worker_id,
        provenance=binding.provenance(),
        validator=binding.validate_task,
    )
    return worker, handoff


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one or more AI26 distributed analysis tasks")
    parser.add_argument("--run-manifest", required=True)
    parser.add_argument("--private-config", required=True)
    parser.add_argument("--codebook", required=True)
    parser.add_argument("--worker-id")
    parser.add_argument("--max-tasks", type=int, default=1)
    parser.add_argument("--reclaim-idle-ms", type=int, default=300_000)
    parser.add_argument(
        "--seed-ready",
        action="store_true",
        help="seed a bounded batch from Collection's Mongo handoff before consuming tasks",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    private_root = os.environ.get("LACLAUGPT_PRIVATE_CONFIG_DIR")
    if not private_root:
        raise SystemExit("LACLAUGPT_PRIVATE_CONFIG_DIR is required")
    env_run_id = os.environ.get("LACLAUGPT_RUN_ID")
    if not env_run_id:
        raise SystemExit("LACLAUGPT_RUN_ID is required")
    binding = WorkerBinding.build(
        manifest_path=args.run_manifest,
        private_root=private_root,
        private_config=args.private_config,
        codebook=args.codebook,
        worker_id=args.worker_id,
    )
    if env_run_id != binding.manifest.run_id:
        raise ValueError("LACLAUGPT_RUN_ID does not match frozen run manifest")
    settings = load_settings()
    worker, handoff = build_worker(binding, settings)
    if args.seed_ready:
        seed_ready_tasks(binding, handoff, worker.queue, limit=max(args.max_tasks, 0))
    worker.heartbeat(run_id=binding.manifest.run_id, status="starting")
    processed = 0
    for _ in range(max(args.max_tasks, 0)):
        status = worker.run_once(reclaim_idle_ms=args.reclaim_idle_ms)
        worker.heartbeat(run_id=binding.manifest.run_id, status=status)
        if status == "idle":
            break
        processed += 1
    worker.heartbeat(run_id=binding.manifest.run_id, status="finished", processed=str(processed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
