"""Sanitized runtime preflight for manual bring-up and cron checks.

Checks the composed configuration and the reachable backends **without printing
credentials**. Output is a JSON report, so a wrapper or an operator can read it
and a log can keep it without leaking secrets.

Used by ``scripts/run_ai26_laskin.sh --check`` and by debug mode.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from .debug_mode import sanitize_url
from .staging import StagingPolicy


def _check_mongodb(settings: Any) -> dict[str, Any]:
    if not settings.mongo_url:
        return {"configured": False, "reachable": None}
    try:
        from pymongo import MongoClient
    except ImportError:
        return {"configured": True, "reachable": None, "error": "pymongo_not_installed"}
    try:
        client = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        client.close()
        return {"configured": True, "reachable": True}
    except Exception as exc:  # noqa: BLE001 - report the class, never the URI
        return {"configured": True, "reachable": False, "error": type(exc).__name__}


def _check_redis(settings: Any) -> dict[str, Any]:
    if not settings.redis_url:
        return {"configured": False, "reachable": None}
    try:
        import redis
    except ImportError:
        return {"configured": True, "reachable": None, "error": "redis_not_installed"}
    try:
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=3)
        client.ping()
        return {"configured": True, "reachable": True}
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "reachable": False, "error": type(exc).__name__}


def _check_object_store(settings: Any) -> dict[str, Any]:
    if settings.object_backend != "s3":
        return {"backend": settings.object_backend, "configured": False}
    if not settings.s3_bucket:
        return {"backend": "s3", "configured": False, "error": "missing_bucket"}
    report: dict[str, Any] = {
        "backend": "s3",
        "configured": True,
        "bucket": settings.s3_bucket,
        "endpoint": sanitize_url(settings.s3_endpoint_url or ""),
    }
    try:
        import boto3
    except ImportError:
        report["error"] = "boto3_not_installed"
        return report
    try:
        client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region or None,
        )
        # A HEAD on a project-scoped sentinel validates credentials without
        # requiring list permission (Allas commonly denies ListBucket).
        prefix = settings.distributed_namespace.s3_key("analysis").rstrip("/")
        client.head_object(Bucket=settings.s3_bucket, Key=f"{prefix}/.preflight")
        report["reachable"] = True
    except Exception as exc:  # noqa: BLE001
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"} or getattr(
            exc, "response", {}
        ).get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
            # Credentials work; the sentinel simply does not exist.
            report["reachable"] = True
        else:
            report["reachable"] = False
            report["error"] = type(exc).__name__
    return report


def _check_ollama(settings: Any) -> dict[str, Any]:
    """Verify the endpoint serves the configured model, without dumping models."""
    report: dict[str, Any] = {
        "mode": settings.llm_mode,
        "model": settings.llm_model,
        "endpoint": sanitize_url(settings.llm_endpoint),
    }
    try:
        import ollama
    except ImportError:
        report["error"] = "ollama_not_installed"
        return report
    try:
        client = ollama.Client(host=settings.llm_endpoint) if settings.llm_endpoint else ollama.Client()
        listed = client.list()
        names = {
            str(item.get("model") or item.get("name") or "")
            for item in (listed.get("models") or [])
        }
        report["reachable"] = True
        report["model_present"] = settings.llm_model in names
    except Exception as exc:  # noqa: BLE001
        report["reachable"] = False
        report["error"] = type(exc).__name__
    return report


def preflight_report() -> dict[str, Any]:
    """Return a credential-free report of the composed runtime configuration."""
    from .config import load_settings

    settings = load_settings()
    staging = StagingPolicy(
        max_cache_bytes=None,
        max_object_bytes=512 * 1024**2,
        max_age_seconds=0,
    )
    report: dict[str, Any] = {
        "status": "ok",
        "project_id": settings.project_id,
        # Run identity is a distributed-run concept; the worker enforces it
        # against the frozen manifest. The preflight reports it when present.
        "run_id": os.environ.get("LACLAUGPT_RUN_ID", ""),
        "machine": settings.machine,
        "execution": settings.execution,
        "storage_backend": settings.storage_backend,
        "deployment": {
            key: value
            for key, value in settings.deployment_profile.provenance_metadata().items()
            if key != "endpoint"
        },
        "llm_endpoint": sanitize_url(settings.llm_endpoint),
        "data_dir": str(settings.data_dir),
        "media_staging": {
            "pruning_enabled": staging.pruning_enabled,
            "max_object_bytes": staging.max_object_bytes,
        },
        "checks": {
            "mongodb": _check_mongodb(settings),
            "redis": _check_redis(settings),
            "object_store": _check_object_store(settings),
            "ollama": _check_ollama(settings),
        },
    }

    problems: list[str] = []
    deployment_errors = settings.deployment_profile.validate()
    problems.extend(deployment_errors)
    checks = report["checks"]
    if checks["mongodb"].get("reachable") is False:
        problems.append("mongodb unreachable")
    if checks["redis"].get("reachable") is False:
        problems.append("redis unreachable")
    if checks["object_store"].get("reachable") is False:
        problems.append("object store unreachable")
    if checks["ollama"].get("reachable") is False:
        problems.append("ollama endpoint unreachable")
    if checks["ollama"].get("model_present") is False:
        problems.append(f"model not present on endpoint: {settings.llm_model}")
    if problems:
        report["status"] = "invalid"
        report["problems"] = problems
    return report


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        report = preflight_report()
    except Exception as exc:  # noqa: BLE001 - a preflight must not crash the wrapper
        print(json.dumps({"status": "error", "error": type(exc).__name__}, indent=2))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
