"""AI26 distributed worker built on the generic task-queue contract.

Redis is coordination only, MongoDB owns durable canonical/result state, and the
existing canonical pipeline performs analysis. Private configuration and codebooks are
verified against a frozen run manifest before any task is processed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import socket
import subprocess
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from .canonical import SCHEMA_VERSION, CanonicalRecord
from .canonical_pipeline import PipelineContext, run_canonical_pipeline
from .codebooks import load_codebook
from .config import Settings, load_settings
from .llm.ollama import (
    LLM_ENDPOINT_ENV_ALIAS,
    LLM_HOST_ENV,
    OllamaProvider,
    configured_llm_modes,
    resolve_llm_host,
)
from .phase1_laskin_runtime import load_ai26_runtime_policy
from .staging import (
    MediaStager,
    ObjectUnavailableError,
    StagingPolicy,
)
from .storage import artifact_store
from .task_queue import (
    DurableTaskStore,
    TaskEnvelope,
    TaskQueue,
    TaskWorker,
    durable_store_from_settings,
    redis_queue_from_settings,
)

logger = logging.getLogger(__name__)

AI26_MODEL = "gemma4:12b"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_project_config(path: Path) -> dict[str, Any]:
    """Read the frozen private project configuration, failing closed on invalid input."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"private project config is unreadable or malformed: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("private project config must be a JSON object")
    return payload


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
    source_tree_sha256: str = ""

    @classmethod
    def load(cls, path: str | Path) -> FrozenRunManifest:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in known})


_SOURCE_TREE_ROOTS = ("src",)
_SOURCE_TREE_SUFFIXES = (".py",)


def _source_tree_sha256(repo_root: Path | None = None) -> str:
    root = repo_root or Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    files: list[Path] = []
    for top in _SOURCE_TREE_ROOTS:
        base = root / top
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in _SOURCE_TREE_SUFFIXES:
                files.append(path)
    for path in sorted(files, key=lambda item: item.as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


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
        frozen_tree = (self.manifest.source_tree_sha256 or "").strip()
        if frozen_tree:
            runtime_tree = _source_tree_sha256()
            if runtime_tree == frozen_tree:
                return
            raise ValueError(
                "analysed source tree has changed since the run was frozen: "
                f"manifest={frozen_tree} runtime={runtime_tree}. "
                "Re-freeze the run with laclaugpt-freeze-ai26 before analysing."
            )
        runtime_sha = _runtime_public_git_sha()
        if runtime_sha != self.manifest.public_git_sha:
            raise ValueError(
                "public Git SHA does not match frozen run manifest: "
                f"manifest={self.manifest.public_git_sha} runtime={runtime_sha}. "
                "Re-freeze the run with laclaugpt-freeze-ai26 before analysing."
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
    for name, mode in configured_llm_modes():
        if mode != "local":
            raise ValueError(
                f"AI26 distributed test forbids cloud/external Ollama mode: {name}={mode}"
            )
    fallback = os.environ.get("LLM_ALLOW_CLOUD_FALLBACK", "").strip().casefold()
    if fallback in {"1", "true", "yes", "on"}:
        raise ValueError("AI26 distributed test forbids cloud fallback")
    configured_model = (
        os.environ.get("LACLAUGPT_LLM_MODEL")
        or os.environ.get("LACLAUGPT_OLLAMA_MODEL")
        or os.environ.get("OLLAMA_MODEL")
        or AI26_MODEL
    )
    if configured_model != AI26_MODEL:
        raise ValueError(f"configured Ollama model must be {AI26_MODEL}")
    os.environ["LLM_MODE"] = "local"
    os.environ["LACLAUGPT_LLM_MODE"] = "local-ollama"
    os.environ["LLM_ALLOW_CLOUD_FALLBACK"] = "0"
    os.environ["LACLAUGPT_LLM_MODEL"] = AI26_MODEL
    os.environ["LACLAUGPT_OLLAMA_MODEL"] = AI26_MODEL
    endpoint = os.environ.get(LLM_ENDPOINT_ENV_ALIAS, "").strip()
    if endpoint and not os.environ.get(LLM_HOST_ENV, "").strip():
        os.environ[LLM_HOST_ENV] = endpoint


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(f"LACLAUGPT_{name}", "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def build_media_stager(settings: Settings) -> MediaStager | None:
    if settings.object_backend != "s3":
        return None
    cache_raw = os.environ.get("LACLAUGPT_STAGING_MAX_CACHE_BYTES", "").strip()
    age_raw = os.environ.get("LACLAUGPT_STAGING_MAX_AGE_SECONDS", "").strip()
    max_cache = int(cache_raw) if cache_raw else 8 * 1024**3
    max_age = int(age_raw) if age_raw else 14 * 24 * 3600
    if max_cache == 0 and max_age == 0:
        max_cache = None
    return MediaStager(
        artifact_store(settings),
        settings.data_path("cache", "media-staging"),
        policy=StagingPolicy(
            max_cache_bytes=max_cache,
            max_object_bytes=_int_env("STAGING_MAX_OBJECT_BYTES", 512 * 1024**2),
            max_age_seconds=max_age,
        ),
        project_id=settings.project_id,
    )


def ready_handoff_query(*, project_id: str, run_id: str, not_before: str | None) -> dict[str, Any]:
    """Build the canonical Collection -> Analysis handoff query.

    Study date boundaries come from the Phase 1 protocol profile. Keeping this
    helper pure makes the boundary contract testable without a live MongoDB.
    """
    query: dict[str, Any] = {
        "project_id": project_id,
        "handoff.status": "ready",
        "handoff.run_id": run_id,
    }
    if not_before:
        query["handoff.published_at"] = {"$gt": not_before}
    return query


class MongoCollectionHandoff:
    def __init__(self, settings: Settings, *, not_before: str | None = None):
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
        self.not_before = not_before

    def resolve(self, source_url: str) -> CanonicalRecord:
        row = self.collection.find_one({"project_id": self.project_id, "source_url": source_url})
        if row is None:
            raise KeyError(f"canonical source not found: {source_url}")
        clean = {key: value for key, value in row.items() if key in CanonicalRecord.model_fields}
        return CanonicalRecord.model_validate(clean)

    def ready_handoffs(self, run_id: str, *, limit: int, offset: int = 0) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        cursor = self.collection.find(
            ready_handoff_query(
                project_id=self.project_id,
                run_id=run_id,
                not_before=self.not_before,
            ),
            {"handoff": 1, "_id": 0},
        ).sort(
            [
                ("handoff.source_priority", 1),
                ("handoff.published_at", -1),
                ("source_url", 1),
            ]
        ).skip(max(offset, 0)).limit(limit)
        return [dict(row.get("handoff") or {}) for row in cursor]


def _flatten_provenance(payload: Any) -> dict[str, list[str]]:
    """Flatten a rich provenance mapping into ``dict[str, list[str]]``.

    ``PipelineContext.provenance`` accepts only lists of strings, while the staging
    report nests structures. Each top-level key becomes a list of rendered values, so
    no information is dropped and the value stays inside the declared contract.
    """

    def render(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, bool | int | float) or value is None:
            return str(value)
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)

    flattened: dict[str, list[str]] = {}
    for key, value in dict(payload or {}).items():
        if isinstance(value, list | tuple):
            flattened[str(key)] = [render(item) for item in value]
        else:
            flattened[str(key)] = [render(value)]
    return flattened


def _publish_local_media_refs(record: Any, report: Any) -> None:
    """Point frames/media at staged local files so the multimodal adapter can attach them.

    A staged path is local runtime state: it is written to the transient frame or media
    reference only, never into canonical source identity.
    """
    by_ref = {item.ref: item for item in report.staged if item.local_available}
    if not by_ref:
        return
    for frame in getattr(record.content, "frames", []) or []:
        ref = getattr(frame, "media_ref", None)
        if ref and ref in by_ref:
            frame.media_ref = str(by_ref[ref].path)
    for media in getattr(record.content, "media_references", []) or []:
        ref = getattr(media, "object_ref", None)
        if ref and ref in by_ref:
            media.local_ref = str(by_ref[ref].path)


class AI26Handler:
    def __init__(
        self,
        binding: WorkerBinding,
        settings: Settings,
        handoff: MongoCollectionHandoff,
        *,
        stager: MediaStager | None = None,
    ):
        self.binding = binding
        self.settings = settings
        self.handoff = handoff
        self.project_config = _load_project_config(binding.private_config)
        self.codebook = load_codebook(binding.codebook)
        # The model is chosen per request by run_canonical_pipeline, so the provider
        # takes the host only. Passing `model=` here is a TypeError.
        self.provider = OllamaProvider(host=resolve_llm_host() or None)
        # Staging is performed explicitly in __call__: the report feeds both provenance
        # and the local media references, and a retriable failure must abort the task.
        # It cannot be handed to PipelineContext — that model declares no stager field
        # and silently drops unknown keys, which would make staging a silent no-op.
        self.stager = stager if stager is not None else build_media_stager(settings)
        # Only declared PipelineContext fields belong here. An undeclared kwarg is
        # discarded without warning, so the manifest revisions are carried in
        # `provenance`, which the context actually keeps (matching the proven working
        # implementation). `config_revision`/`codebook_revision` are left for the
        # analysis stages to fill from the run manifest.
        self.context = PipelineContext(
            project_context="AI26 distributed bounded test",
            project_config=self.project_config,
            provenance={
                "private_config_sha256": [binding.manifest.config_sha256],
                "codebook_sha256": [binding.manifest.codebook_sha256],
            },
        )

    def __call__(self, task: TaskEnvelope) -> dict[str, Any]:
        record = self.handoff.resolve(task.record_ref)
        context = self.context
        if self.stager is not None:
            # Materialise referenced objects before any multimodal model call. A
            # retriable failure aborts so the task retries instead of silently
            # producing a degraded scientific result.
            report = self.stager.stage_record(record)
            retriable = [item for item in report.staged if item.retriable]
            if retriable:
                raise ObjectUnavailableError(
                    "media staging failed (retriable): "
                    + ", ".join(f"{item.cache_key}:{item.reason}" for item in retriable)
                )
            _publish_local_media_refs(record, report)
            context = context.model_copy(
                update={
                    "provenance": {
                        **context.provenance,
                        **_flatten_provenance(report.provenance()),
                    }
                }
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
        self.last_failure_class: str | None = None
        quarantine_before = int(getattr(self.queue, "quarantined_count", 0))
        self.last_quarantined = 0
        claimed = None
        if reclaim_idle_ms is not None:
            claimed = self.queue.reclaim(min_idle_ms=reclaim_idle_ms)
        if claimed is None:
            claimed = self.queue.claim()
        self.last_quarantined = max(
            0,
            int(getattr(self.queue, "quarantined_count", 0)) - quarantine_before,
        )
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
            inserted = self.durable_store.write_result(task, result, self.provenance)
            self.queue.ack(claimed.message_id)
            return "completed" if inserted else "duplicate"
        except Exception as exc:
            self.last_failure_class = type(exc).__name__
            error = f"{self.last_failure_class}: {exc}"
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
    durable_store: DurableTaskStore,
    *,
    limit: int,
    page_size: int | None = None,
) -> int:
    if limit < 1:
        return 0
    batch_size = max(1, page_size or limit)
    count = 0
    offset = 0
    while count < limit:
        envelopes = handoff.ready_handoffs(binding.manifest.run_id, limit=batch_size, offset=offset)
        if not envelopes:
            break
        offset += len(envelopes)
        for envelope in envelopes:
            task = binding.task_from_handoff(envelope)
            if durable_store.has_result(task.idempotency_key):
                continue
            queue.publish(task)
            count += 1
            if count >= limit:
                break
        if len(envelopes) < batch_size:
            break
    return count


def build_worker(binding: WorkerBinding, settings: Settings) -> tuple[TaskWorker, MongoCollectionHandoff]:
    binding.validate_runtime_code()
    enforce_local_model(binding.manifest)
    policy = load_ai26_runtime_policy()
    if settings.project_id != binding.manifest.project_id:
        raise ValueError("settings project_id does not match frozen run manifest")
    if settings.project_id != policy.study_id:
        raise ValueError("settings project_id does not match canonical Phase 1 AI26 profile")
    queue = redis_queue_from_settings(
        settings,
        run_id=binding.manifest.run_id,
        worker_id=binding.worker_id,
    )
    durable = durable_store_from_settings(settings, run_id=binding.manifest.run_id)
    handoff = MongoCollectionHandoff(settings, not_before=policy.date_after)
    worker_provenance = {**binding.provenance(), **policy.provenance()}
    worker = AI26TaskWorker(
        queue=queue,
        durable_store=durable,
        handler=AI26Handler(binding, settings, handoff),
        worker_id=binding.worker_id,
        provenance=worker_provenance,
        validator=binding.validate_task,
    )
    return worker, handoff


def _cycle_exit_code(counts: dict[str, int]) -> int:
    failures = counts.get("retry", 0) + counts.get("dead-letter", 0)
    if counts.get("completed", 0) == 0 and failures > 0:
        return 1
    return 0


def _cycle_exit_status(
    *,
    attempted: int,
    completed: int,
    duplicate: int = 0,
    retry: int = 0,
    dead_letter: int = 0,
) -> int:
    """Compatibility helper used by regression tests for issue #101."""
    if attempted <= 0 or completed > 0 or duplicate == attempted:
        return 0
    if retry == 0 and dead_letter == 0:
        return 0
    return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one or more AI26 distributed analysis tasks")
    parser.add_argument("--run-manifest", required=True)
    parser.add_argument("--private-config", required=True)
    parser.add_argument("--codebook", required=True)
    parser.add_argument("--worker-id")
    parser.add_argument("--max-tasks", type=int, default=10)
    parser.add_argument("--reclaim-idle-ms", type=int, default=900_000)
    parser.add_argument("--seed-ready", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    private_root = os.environ.get("LACLAUGPT_PRIVATE_CONFIG_DIR", "")
    if not private_root:
        raise SystemExit("LACLAUGPT_PRIVATE_CONFIG_DIR is required")
    settings = load_settings()
    binding = WorkerBinding.build(
        manifest_path=args.run_manifest,
        private_root=private_root,
        private_config=args.private_config,
        codebook=args.codebook,
        worker_id=args.worker_id,
    )
    worker, handoff = build_worker(binding, settings)
    if args.seed_ready:
        seed_ready_tasks(
            binding,
            handoff,
            worker.queue,
            worker.durable_store,
            limit=max(args.max_tasks, 0),
        )
    counts = {
        "completed": 0,
        "duplicate": 0,
        "retry": 0,
        "dead-letter": 0,
        "quarantined": 0,
        "idle": 0,
    }
    for _ in range(max(args.max_tasks, 0)):
        outcome = worker.run_once(reclaim_idle_ms=args.reclaim_idle_ms)
        counts[outcome] = counts.get(outcome, 0) + 1
        counts["quarantined"] += int(getattr(worker, "last_quarantined", 0))
        if outcome == "idle":
            break
    logger.info("AI26 worker cycle: %s", counts)
    return _cycle_exit_code(counts)


if __name__ == "__main__":
    raise SystemExit(main())
