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
from uuid import uuid4

from .debug_mode import sanitize_url
from .staging import StagingPolicy
from .storage import S3ArtifactStore


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
        "endpoint": sanitize_url(settings.s3_endpoint_url or "shared-aws-config"),
        "signature_version": settings.s3_signature_version,
        "addressing_style": settings.s3_addressing_style,
    }
    try:
        store = S3ArtifactStore(
            settings.s3_bucket,
            settings.s3_endpoint_url,
            settings.s3_region,
            prefix=settings.distributed_namespace.s3_key("analysis").rstrip("/"),
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            signature_version=settings.s3_signature_version,
            addressing_style=settings.s3_addressing_style,
        )
        # Verify the exact write path the pipeline needs. The tiny sentinel stays
        # inside this project's namespace and is deleted immediately afterwards.
        key = f".preflight/{uuid4().hex}.txt"
        store.put_bytes(key, b"laclaugpt-preflight\n", content_type="text/plain")
        report["reachable"] = True
        report["writeable"] = True
        try:
            store.delete(key)
            report["cleanup"] = True
        except Exception as exc:  # noqa: BLE001 - upload capability already proven
            report["cleanup"] = False
            report["cleanup_error"] = type(exc).__name__
    except RuntimeError as exc:
        if "S3 support requires" in str(exc):
            report["error"] = "boto3_not_installed"
            return report
        report["reachable"] = False
        report["writeable"] = False
        report["error"] = type(exc).__name__
    except Exception as exc:  # noqa: BLE001
        report["reachable"] = False
        report["writeable"] = False
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
    if checks["object_store"].get("writeable") is False:
        problems.append("object store is not writeable")
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
