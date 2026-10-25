"""AI26 distributed worker built on the generic task-queue contract.

Redis is coordination only, MongoDB owns durable canonical/result state, and the
existing canonical pipeline performs analysis. Private configuration and codebooks are
verified against a frozen run manifest before any task is processed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
from .debug_mode import configure_logging
from .llm.base import LLMTruncationError, generation_fingerprint
from .llm.ollama import (
    LLM_ENDPOINT_ENV_ALIAS,
    LLM_HOST_ENV,
    OllamaProvider,
    configured_llm_modes,
    resolve_llm_host,
)
from .llm.structured_output import effective_structured_options, structured_output_ceiling
from .phase1_laskin_runtime import load_ai26_runtime_policy
from .staging import (
    MediaStager,
    ObjectUnavailableError,
    StagingPolicy,
)
from .storage import artifact_store, mongo_client
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

#: The prompt identity the worker's stages run under. It must match the default of
#: ``stages.runner.run_canonical_pipeline``; a changed prompt version invalidates resume.
AI26_PROMPT_VERSION = "canonical-pipeline-v1"


def ai26_generation_fingerprint(
    *, model: str = AI26_MODEL, prompt_version: str = AI26_PROMPT_VERSION
) -> str:
    """Fingerprint of the generation settings this worker will actually use.

    Covers the model, the configured mode, every effective generation option (merged
    defaults plus the structured-output budgets, read from the environment) and the
    prompt version. Read-only and network-free: it never probes the endpoint.
    """
    configured = configured_llm_modes()
    mode = configured[0][1] if configured else "local"
    return generation_fingerprint(
        model=model,
        options=effective_structured_options(),
        mode=mode,
        prompt_version=prompt_version,
    )


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
    """Refuse to start a worker that cannot honestly serve every task.

    These checks run before the first claim, so a misconfigured worker exits without
    taking work it cannot finish. The provider dependency is one of them: without the
    ``ollama`` package every call raises lazily *after* the task has been claimed, which
    turns one configuration error into a claimed-then-failed task (issue #372, upstream
    #292/#293: the preflight must name the missing dependency, not discover it mid-run).
    """
    if manifest.model != AI26_MODEL:
        raise ValueError(f"AI26 distributed test requires model {AI26_MODEL}")
    if importlib.util.find_spec("ollama") is None:
        raise ValueError(
            "the ollama package is required for the AI26 worker; "
            "install it with pip install -e '.[ollama]' before claiming tasks"
        )
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
        self.collection = mongo_client(settings.mongo_url)[settings.mongo_database][
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
        # Each record gets isolated project/context state. Analysis stages may update
        # provenance or nested configuration while processing; sharing those mutations
        # with subsequent records makes results order-dependent (EP24 #301 class).
        context = self.context.model_copy(deep=True)
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


def _maybe_rearm_terminal_failure_for_higher_budget(
    durable_store: DurableTaskStore, idempotency_key: str
) -> int:
    """Best-effort compatibility hook for stores that support #321 auto-rearm."""
    rearm = getattr(durable_store, "rearm_terminal_failure_if_budget_increased", None)
    if not callable(rearm):
        return 0
    return int(rearm(idempotency_key, structured_output_ceiling()))


def _failure_diagnostics(exc: Exception) -> dict[str, Any]:
    """Extract structured-output evidence attached at the LLM boundary."""
    response_raw = getattr(exc, "response_raw", None)
    finish_reason = getattr(exc, "finish_reason", None)
    if response_raw is None and finish_reason is None:
        return {}
    diagnostics = {
        "response_raw": "" if response_raw is None else str(response_raw),
        "finish_reason": "" if finish_reason is None else str(finish_reason),
    }
    decode_details = getattr(exc, "decode_diagnostics", None)
    if isinstance(decode_details, dict):
        diagnostics.update(decode_details)
    if isinstance(exc, LLMTruncationError):
        diagnostics.update({
            "terminal_reason": "unanalysable_within_budget",
            "output_budget_tokens": getattr(exc, "output_budget_tokens", 0),
            "required_output_tokens_lower_bound": getattr(exc, "required_output_tokens_lower_bound", 0),
            "generated_output_chars": getattr(
                exc, "generated_output_chars", len(diagnostics["response_raw"])
            ),
        })
    return diagnostics


class AI26TaskWorker(TaskWorker):
    """Task worker with explicit retry requeue so attempt counters actually advance."""

    def run_once(self, *, reclaim_idle_ms: int | None = None) -> str:
        self.last_failure_class: str | None = None
        self.last_resume_invalidated = 0
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
            try:
                self.validator(task)
            except Exception as exc:
                # Validation failures are terminal for this immutable task envelope.
                # Persist and quarantine them immediately so a stale revision cannot
                # poison the head of either the fresh or reclaimed queue.
                self.last_failure_class = type(exc).__name__
                error = f"{self.last_failure_class}: {exc}"
                self.durable_store.write_failure(
                    task,
                    error,
                    self.provenance,
                    terminal=True,
                )
                self.queue.dead_letter(task, error)
                self.queue.ack(claimed.message_id)
                return "dead-letter"
        if self.has_current_result(task):
            self.queue.ack(claimed.message_id)
            return "duplicate"
        if self.durable_store.has_terminal_failure(task.idempotency_key):
            rearmed = _maybe_rearm_terminal_failure_for_higher_budget(
                self.durable_store, task.idempotency_key
            )
            if rearmed:
                logger.info(
                    "Automatically re-armed %s terminal truncation failure record(s) "
                    "for %s after structured-output ceiling increase",
                    rearmed,
                    task.idempotency_key,
                )
            if self.durable_store.has_terminal_failure(task.idempotency_key):
                self.queue.ack(claimed.message_id)
                return "duplicate"
        try:
            result = self.handler(task)
            inserted = self.durable_store.write_result(
                task,
                result,
                self.provenance,
                fingerprint=self.generation_fingerprint,
            )
            self.queue.ack(claimed.message_id)
            return "completed" if inserted else "duplicate"
        except Exception as exc:
            self.last_failure_class = type(exc).__name__
            error = f"{self.last_failure_class}: {exc}"
            # A second length stop has already exhausted the structured call's
            # escalation. Replaying the same immutable task cannot help; require
            # explicit re-arm after changing the prompt/model/configuration.
            terminal = isinstance(exc, LLMTruncationError) or task.attempt >= self.max_attempts
            self.durable_store.write_failure(
                task,
                error,
                self.provenance,
                diagnostics=_failure_diagnostics(exc),
                terminal=terminal,
            )
            if terminal:
                self.queue.dead_letter(task, error)
                self.queue.ack(claimed.message_id)
                return "dead-letter"
            retry_task = replace(task, attempt=task.attempt + 1)
            retry_task.validate()
            self.queue.publish(retry_task)
            self.queue.ack(claimed.message_id)
            return "retry"


#: How many rejected handoffs a single seeding pass names individually before summarising the rest.
#: One bad row must be visible, but a corpus-wide identity regression must not fill the log.
_REJECTION_DETAIL_LIMIT = 20

#: What a seed cycle found when it published nothing. A cycle that publishes
#: nothing is not one situation but several, and before #382 they were
#: indistinguishable in the cron log.
SEED_SEEDED = "seeded"
SEED_BUDGET_ZERO = "budget_zero"
SEED_UPSTREAM_EMPTY = "upstream_empty"
SEED_ALL_REJECTED = "all_rejected"
SEED_NO_NEW_WORK = "no_new_work"


def seed_disposition(diagnostics: dict[str, int]) -> str:
    """Classify a seed cycle from its counts, without touching a queue or a store.

    ``upstream_empty`` is the one that matters: it means Collection handed over
    nothing for this run at all, so an idle analysis cycle is *not* evidence that
    the corpus is fully analysed. It may equally mean the frozen run id, the
    project id, or the Phase 1 date window no longer matches what Collection is
    publishing -- a pipeline that is silently reading nothing looks exactly like a
    pipeline with nothing left to do.

    ``all_rejected`` is its mirror image and must not be confused with it: rows *did*
    arrive, and every one of them was refused. Reporting that as "no new work" would
    turn an identity regression into a quiet queue.

    This is the complement of the handoff quarantine: the quarantine names rows that
    arrived and could not be used, this names what the zero means.
    """
    if diagnostics.get("published", 0) > 0:
        return SEED_SEEDED
    if diagnostics.get("limit", 0) < 1:
        return SEED_BUDGET_ZERO
    if diagnostics.get("examined", 0) == 0:
        return SEED_UPSTREAM_EMPTY
    if diagnostics.get("rejected", 0) > 0 and diagnostics["rejected"] >= diagnostics["examined"]:
        return SEED_ALL_REJECTED
    return SEED_NO_NEW_WORK


def seed_ready_tasks(
    binding: WorkerBinding,
    handoff: MongoCollectionHandoff,
    queue: TaskQueue,
    durable_store: DurableTaskStore,
    *,
    limit: int,
    page_size: int | None = None,
    fingerprint: str = "",
    rejected: list[dict[str, str]] | None = None,
    diagnostics: dict[str, int] | None = None,
) -> int:
    """Queue ready handoffs, quarantining any that cannot become a task (issue #382).

    A ready handoff that is missing its identity -- no ``source_url``, no ``handoff_key``, or a
    ``run_id`` that does not match the frozen manifest -- raises inside
    :meth:`WorkerBinding.task_from_handoff`. Before this change that exception propagated out of
    the whole seeding pass, so **one malformed row stopped every remaining record in the batch and
    every later tick re-read the same row and failed again**: the pipeline stalled until a human
    noticed, and the stall looked like an idle cycle rather than a refusal.

    The upstream Multimodal-Analysis fixes #299, #303 and #304 all describe this class from three
    angles: one unidentifiable media row crashed a country batch, identity had to be *recovered*
    where it was provable, and rows that could not be identified at all had to be quarantined with
    an audit rather than dropped or allowed to block the job.

    So a rejected handoff is now **skipped, named and counted** -- never silently discarded, because
    it stays in the collection and stays visible:

    * if ``rejected`` is given, one record per rejection is appended with the handoff key and the
      reason, so a caller can persist or report it;
    * the first :data:`_REJECTION_DETAIL_LIMIT` are logged individually and the remainder summed,
      so a systemic failure is loud once rather than loud ten thousand times;
    * seeding continues, and the record stays ``ready`` upstream, so the next tick retries it. A
      quarantine is not a deletion.

    The two out-parameters answer different halves of the same question. ``rejected`` explains rows
    that *arrived and could not be used*. ``diagnostics`` explains a pass that published **nothing**,
    where the counts behind the zero are the whole answer: work already done at this generation,
    permanent failures, a zero budget, or nothing handed over at all. Without it those cases were
    the same empty log line. See :func:`seed_disposition`.

    Return value stays the number of tasks **published**, so the meaning a caller already relies on
    is unchanged.
    """
    counts = {
        "limit": max(limit, 0),
        "examined": 0,
        "published": 0,
        "already_analyzed": 0,
        "terminal_failure": 0,
        "rearmed": 0,
        "rejected": 0,
    }
    rejections = 0
    try:
        if limit < 1:
            return 0
        batch_size = max(1, page_size or limit)
        offset = 0
        while counts["published"] < limit:
            envelopes = handoff.ready_handoffs(
                binding.manifest.run_id, limit=batch_size, offset=offset
            )
            if not envelopes:
                break
            offset += len(envelopes)
            counts["examined"] += len(envelopes)
            for envelope in envelopes:
                try:
                    task = binding.task_from_handoff(envelope)
                except (KeyError, TypeError, ValueError) as exc:
                    rejections += 1
                    record = {
                        "handoff_key": str(envelope.get("handoff_key") or ""),
                        "run_id": str(envelope.get("run_id") or ""),
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                    if rejected is not None:
                        rejected.append(record)
                    if rejections <= _REJECTION_DETAIL_LIMIT:
                        logger.warning(
                            "AI26 handoff quarantined at seed: handoff_key=%s reason=%s "
                            "(it stays ready upstream and is retried next cycle)",
                            record["handoff_key"] or "<missing>",
                            record["reason"],
                        )
                    continue
                if durable_store.has_result(task.idempotency_key, fingerprint):
                    counts["already_analyzed"] += 1
                    continue
                if durable_store.has_terminal_failure(task.idempotency_key):
                    rearmed = _maybe_rearm_terminal_failure_for_higher_budget(
                        durable_store, task.idempotency_key
                    )
                    if rearmed:
                        counts["rearmed"] += rearmed
                        logger.info(
                            "Automatically re-armed %s terminal truncation failure record(s) "
                            "for %s during seed after structured-output ceiling increase",
                            rearmed,
                            task.idempotency_key,
                        )
                    if durable_store.has_terminal_failure(task.idempotency_key):
                        counts["terminal_failure"] += 1
                        continue
                queue.publish(task)
                counts["published"] += 1
                if counts["published"] >= limit:
                    break
            if len(envelopes) < batch_size:
                break
        counts["rejected"] = rejections
        if rejections > _REJECTION_DETAIL_LIMIT:
            logger.error(
                "AI26 handoff quarantine: %d ready handoff(s) could not become tasks this cycle; "
                "%d named individually above, %d more suppressed. They remain ready upstream and "
                "will be retried, so this will repeat every cycle until the identities are repaired.",
                rejections,
                _REJECTION_DETAIL_LIMIT,
                rejections - _REJECTION_DETAIL_LIMIT,
            )
        return counts["published"]
    finally:
        if diagnostics is not None:
            diagnostics.clear()
            diagnostics.update(counts)


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
    fingerprint = ai26_generation_fingerprint()
    worker_provenance = {**worker_provenance, "generation_fingerprint": fingerprint}
    worker = AI26TaskWorker(
        queue=queue,
        durable_store=durable,
        handler=AI26Handler(binding, settings, handoff),
        worker_id=binding.worker_id,
        provenance=worker_provenance,
        validator=binding.validate_task,
        generation_fingerprint=fingerprint,
    )
    return worker, handoff


def _cycle_exit_code(counts: dict[str, int]) -> int:
    failures = counts.get("retry", 0) + counts.get("dead-letter", 0)
    if counts.get("completed", 0) == 0 and failures > 0:
        return 1
    if counts.get("seeded", 0) > 0 and counts.get("completed", 0) == 0:
        return 1
    return 0


def _run_bounded_cycle(
    worker: TaskWorker,
    *,
    max_tasks: int,
    reclaim_idle_ms: int | None,
    max_claims: int | None = None,
    seeded: int = 0,
) -> tuple[dict[str, int], dict[str, int]]:
    """Run a bounded cycle where duplicate claims do not consume the work budget.

    max_tasks bounds non-duplicate outcomes (completed/retry/dead-letter).
    max_claims independently caps queue scanning so a pathological stale stream
    cannot create an unbounded cycle.
    """
    work_limit = max(max_tasks, 0)
    claim_limit = (
        max(max_claims, 0)
        if max_claims is not None
        else max(1000, work_limit * 100)
    )
    counts = {
        "completed": 0,
        "duplicate": 0,
        "retry": 0,
        "dead-letter": 0,
        "quarantined": 0,
        "idle": 0,
        "seeded": max(seeded, 0),
        "claims": 0,
        "resume_invalidated": 0,
    }
    failure_classes: dict[str, int] = {}
    work_units = 0
    while work_units < work_limit and counts["claims"] < claim_limit:
        outcome = worker.run_once(reclaim_idle_ms=reclaim_idle_ms)
        counts["claims"] += 1
        counts[outcome] = counts.get(outcome, 0) + 1
        counts["quarantined"] += int(getattr(worker, "last_quarantined", 0))
        counts["resume_invalidated"] += int(getattr(worker, "last_resume_invalidated", 0))
        failure_class = getattr(worker, "last_failure_class", None)
        if failure_class:
            failure_classes[failure_class] = failure_classes.get(failure_class, 0) + 1
        if outcome == "idle":
            break
        if outcome != "duplicate":
            work_units += 1
    return counts, failure_classes

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
    parser.add_argument(
        "--max-claims",
        type=int,
        default=None,
        help=(
            "Safety cap on queue entries examined in one cycle. "
            "--max-tasks counts non-duplicate work, not stale duplicate claims."
        ),
    )
    parser.add_argument("--reclaim-idle-ms", type=int, default=900_000)
    parser.add_argument("--seed-ready", action="store_true")
    parser.add_argument(
        "--rearm-failed",
        action="append",
        default=[],
        metavar="IDEMPOTENCY_KEY",
        help="Re-arm a terminally failed document so a later seed cycle may retry it.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # The worker reports its per-cycle counts and diagnostics through the
    # ``laclaugpt_data_analysis`` logger. Without an installed handler those
    # INFO records fall back to ``logging.lastResort`` (WARNING) and are
    # dropped, so the cron log only ever showed warnings and the documented
    # LACLAUGPT_DEBUG=1 verbose mode was inert. Install the debug-mode
    # configuration first so the cycle summary reaches stderr (the cron log)
    # on every run, at INFO by default and DEBUG when requested.
    configure_logging()
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
    for idempotency_key in args.rearm_failed:
        rearmed = worker.durable_store.rearm_terminal_failure(idempotency_key)
        logger.info("Re-armed terminal failure %s: records=%d", idempotency_key, rearmed)
    seeded = 0
    rejected_handoffs: list[dict[str, str]] = []
    seed_diagnostics: dict[str, int] = {}
    if args.seed_ready:
        seeded = seed_ready_tasks(
            binding,
            handoff,
            worker.queue,
            worker.durable_store,
            limit=max(args.max_tasks, 0),
            fingerprint=worker.generation_fingerprint,
            rejected=rejected_handoffs,
            diagnostics=seed_diagnostics,
        )
        disposition = seed_disposition(seed_diagnostics)
        if disposition == SEED_UPSTREAM_EMPTY:
            # An idle analysis cycle and an empty upstream are the same log line
            # unless this is said out loud. Do not let a drained queue stand in
            # for a drained corpus.
            logger.warning(
                "AI26 seed found no ready handoff for run %s (examined=0 limit=%d): "
                "Collection handed over nothing. Confirm the frozen run id, project_id "
                "and Phase 1 date window before reading an idle cycle as a complete corpus.",
                binding.manifest.run_id,
                args.max_tasks,
            )
        else:
            logger.info(
                "AI26 seed disposition=%s run=%s %s",
                disposition,
                binding.manifest.run_id,
                seed_diagnostics,
            )
    counts, failure_classes = _run_bounded_cycle(
        worker,
        max_tasks=args.max_tasks,
        reclaim_idle_ms=args.reclaim_idle_ms,
        max_claims=args.max_claims,
        seeded=seeded,
    )
    if (
        seeded > 0
        and counts["completed"] == 0
        and counts["retry"] == 0
        and counts["dead-letter"] == 0
    ):
        logger.warning(
            "AI26 worker made no analysis progress despite %d newly seeded ready task(s); "
            "claims=%d duplicates=%d",
            seeded,
            counts["claims"],
            counts["duplicate"],
        )
    failure_summary = worker.durable_store.failure_summary()
    counts["handoff_rejected"] = len(rejected_handoffs)
    logger.info(
        "AI26 worker cycle: %s failure_classes=%s failure_summary=%s",
        counts,
        failure_classes,
        failure_summary,
    )
    if rejected_handoffs:
        logger.error(
            "AI26 handoff quarantine this cycle: %d ready handoff(s) could not be turned into "
            "tasks and were skipped, not deleted. First key: %s",
            len(rejected_handoffs),
            rejected_handoffs[0]["handoff_key"] or "<missing>",
        )
    return _cycle_exit_code(counts)


if __name__ == "__main__":
    raise SystemExit(main())
