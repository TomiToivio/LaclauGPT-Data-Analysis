"""Distributed AI26 analysis worker CLI (Roihu Slurm + Linux server).

Binds the shared contract together:

1. resolve the environment contract (fail closed);
2. load/freeze the run manifest (model/codebook/config/schema versions);
3. verify the local Ollama ``gemma4:12b`` availability (no cloud fallback);
4. claim jobs atomically under Redis lease;
5. run canonical analysis on the claimed record;
6. write the durable result to MongoDB **before** queue acknowledgement;
7. report researcher-safe status.

Usage examples::

    # bounded Slurm batch (see umbrella deploy/ai26-distributed/roihu.sbatch.example)
    python -m laclaugpt_data_analysis.distributed_worker \\
        --run-id "$LACLAUGPT_RUN_ID" --project-id ai26 --max-jobs 10 --worker-id roihu-1

    # long-running Linux server worker
    python -m laclaugpt_data_analysis.distributed_worker --loop \\
        --run-id "$LACLAUGPT_RUN_ID" --worker-id pouta-analysis-1

    # read-only researcher status
    python -m laclaugpt_data_analysis.distributed_worker status --run-id "$LACLAUGPT_RUN_ID"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from .distributed_env import (
    OLLAMA_HOST_ENV,
    RUN_ID_ENV,
    TEST_MODEL,
    enforce_local_model_policy,
    resolve_distributed_env,
)
from .distributed_jobs import (
    DistributedJobCoordinator,
    enqueue_jobs,
)
from .run_manifest import (
    dump_manifest,
    load_or_freeze_manifest,
    manifest_mismatches,
)


def _lazy_clients(env: Any) -> tuple[Any, Any, Any, Any]:
    """Create Redis + MongoDB clients; deps are optional extras."""
    try:
        import redis
        from pymongo import MongoClient
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "distributed worker requires the [remote] extra: pip install '.[remote]'"
        ) from exc
    redis_client = redis.Redis.from_url(env.redis_url, decode_responses=True)
    mongo = MongoClient(env.mongodb_uri)
    database = mongo["laclaugpt"]
    return (
        redis_client,
        database[f"{env.project_id}__jobs"],
        database[f"{env.project_id}__results"],
        database[f"{env.project_id}__runs"],
    )


def verify_local_model(env: Any, model: str = TEST_MODEL) -> None:
    """Fail closed when the per-host Ollama does not serve the frozen model."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed scheme from env contract
            f"{env.ollama_host.rstrip('/')}/api/tags", timeout=10
        ) as response:
            tags = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"local Ollama unreachable at {env.ollama_host}") from exc
    names = {str(entry.get("name", "")) for entry in tags.get("models", [])}
    if model not in names:
        raise RuntimeError(
            f"model {model!r} not available on local Ollama {env.ollama_host}; "
            "cloud fallback is forbidden in the AI26 distributed test"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="laclaugpt-distributed-worker")
    parser.add_argument("--run-id", default=os.environ.get(RUN_ID_ENV))
    parser.add_argument("--project-id", default="ai26")
    parser.add_argument("--worker-id", default=None)
    parser.add_argument("--max-jobs", type=int, default=0, help="0 = unbounded")
    parser.add_argument("--loop", action="store_true", help="poll forever")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--lease-seconds", type=int, default=600)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument(
        "command",
        nargs="?",
        choices=("run", "freeze-manifest", "status", "enqueue"),
        default="run",
    )
    return parser


def _records_from_stdin() -> list[dict[str, Any]]:
    payload = sys.stdin.read().strip()
    if not payload:
        return []
    return [dict(item) for item in json.loads(payload)]


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    command = args.command

    if command == "status":
        return _status(args)
    return _run(args, freeze_only=command == "freeze-manifest", enqueue=command == "enqueue")


def _status(args: argparse.Namespace) -> int:
    env = resolve_distributed_env(
        default_project_id=args.project_id, require_private_config=False
    )
    _, jobs, results, runs = _lazy_clients(env)
    from .run_manifest import load_or_freeze_manifest

    frozen = load_or_freeze_manifest(
        run_id=env.run_id,
        project_id=env.project_id,
        worker_id=env.worker_id,
        private_config_dir=env.private_config_dir,
        manifest_store=runs,
    )
    coordinator = DistributedJobCoordinator(
        _redis_stub_client(), jobs, results,
        project_id=env.project_id, run_id=env.run_id, worker_id=env.worker_id,
        manifest=frozen,
    )
    print(json.dumps(coordinator.status(), ensure_ascii=False, indent=2, sort_keys=True))
    print(f"manifest: {dump_manifest(frozen)}")
    return 0


def _redis_stub_client():
    """Status needs no Redis lease operations; a no-op client keeps it read-only."""
    class _NoRedis:
        def set(self, *a: Any, **k: Any) -> bool:  # pragma: no cover
            return False

        def get(self, *a: Any, **k: Any) -> None:  # pragma: no cover
            return None

        def delete(self, *a: Any, **k: Any) -> None:  # pragma: no cover
            return None

        def xadd(self, *a: Any, **k: Any) -> None:  # pragma: no cover
            return None

        def expire(self, *a: Any, **k: Any) -> None:  # pragma: no cover
            return None

    return _NoRedis()


def _run(args: argparse.Namespace, *, freeze_only: bool, enqueue: bool) -> int:
    env = resolve_distributed_env(default_project_id=args.project_id)
    model = TEST_MODEL
    enforce_local_model_policy(model)

    redis_client, jobs, results, runs = _lazy_clients(env)
    manifest = load_or_freeze_manifest(
        run_id=env.run_id,
        project_id=env.project_id,
        worker_id=args.worker_id or env.worker_id,
        private_config_dir=env.private_config_dir,
        manifest_store=runs,
    )
    mismatches = manifest_mismatches(
        manifest, model=model, private_config_dir=env.private_config_dir
    )
    if mismatches:
        for reason in mismatches:
            print(f"FAIL closed: {reason}", file=sys.stderr)
        return 3
    verify_local_model(env, model)

    if freeze_only:
        print(dump_manifest(manifest))
        return 0

    if enqueue:
        records = _records_from_stdin()
        created = enqueue_jobs(
            jobs,
            run_id=env.run_id,
            project_id=env.project_id,
            records=records,
        )
        print(f"enqueued {created} jobs for run {env.run_id}")
        return 0

    worker_id = args.worker_id or env.worker_id
    coordinator = DistributedJobCoordinator(
        redis_client,
        jobs,
        results,
        project_id=env.project_id,
        run_id=env.run_id,
        worker_id=worker_id,
        lease_seconds=args.lease_seconds,
        max_attempts=args.max_attempts,
        manifest=manifest,
    )

    from .codebooks import load_codebook
    from .llm.ollama import OllamaProvider
    from .pipeline import analyze_record
    from .run_manifest import discover_codebook

    processed = 0
    failures = 0
    codebook = load_codebook(discover_codebook(env.private_config_dir))
    while args.max_jobs <= 0 or processed < args.max_jobs:
        outcome = coordinator.claim_next()
        if outcome is None or not outcome.claimed:
            if not args.loop:
                break
            time.sleep(args.poll_seconds)
            continue
        job = outcome.job
        try:
            record = _load_canonical_record(env, job)
            provider = OllamaProvider(
                host=os.environ.get(OLLAMA_HOST_ENV, env.ollama_host),
            )
            analyzed = analyze_record(
                record,
                provider=provider,
                codebook_entries=list(codebook.entries),
                model=model,
            )
            result = {
                "analysis": analyzed.canonical_dict()["analysis"],
                "human_readable": analyzed.canonical_dict()["human_readable"],
                "provenance": analyzed.canonical_dict()["provenance"],
                "analysis_version": job.analysis_version,
                "manifest": {
                    "run_id": env.run_id,
                    "model": model,
                    "config_hashes": manifest["config_hashes"],
                    "worker_id": worker_id,
                },
            }
            coordinator.complete(job, result)
            processed += 1
            print(f"done: {job.job_id} arena={job.arena}", flush=True)
        except Exception as exc:  # noqa: BLE001 - worker must survive failures
            coordinator.fail(job, str(exc))
            failures += 1
            print(f"failed: {job.job_id}: {type(exc).__name__}", flush=True)
            if args.max_jobs and processed >= args.max_jobs:
                break
    print(f"worker {worker_id} finished: processed={processed} failures={failures}")
    return 0


def _load_canonical_record(env: Any, job: Any) -> Any:
    """Load the canonical record for a job from the records collection."""
    try:
        from pymongo import MongoClient
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("distributed worker requires '.[remote]'") from exc
    client = MongoClient(env.mongodb_uri)
    database = client["laclaugpt"]
    doc = database[f"{env.project_id}__records"].find_one({"source_url": job.source_url})
    if doc is None:
        raise RuntimeError(f"canonical record not found for {job.source_url}")
    doc.pop("_id", None)
    from .canonical import CanonicalRecord

    return CanonicalRecord.model_validate(doc)


if __name__ == "__main__":
    raise SystemExit(main())