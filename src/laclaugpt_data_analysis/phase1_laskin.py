"""Bounded, opt-in Phase 1 text runner for Laskin side-by-side validation.

The runner consumes copied Phase 0 JSONL and never claims the live Phase 0 queue.
It is deliberately text-only, bounded, and disabled by default.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .interchange import record_to_json
from .phase1_runtime import Phase1TextConfig, run_phase1_text_record

DEFAULT_MAX_RECORDS = 5


def _flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def phase1_laskin_preflight(
    *,
    input_path: Path | None = None,
    config: Phase1TextConfig | None = None,
) -> dict[str, Any]:
    """Return a credential-free readiness report for the bounded Phase 1 path."""
    cfg = config or Phase1TextConfig.from_env()
    report: dict[str, Any] = {
        "status": "ok",
        "enabled": cfg.enabled,
        "discourse_enabled": cfg.discourse_enabled,
        "project_profile": cfg.project_profile,
        "cloud_fallback": cfg.allow_cloud_fallback,
        "phase2_enabled": False,
        "text_only": True,
        "multimodal_required": False,
        "browser_required": False,
        "input": str(input_path) if input_path else None,
        "checks": {},
    }
    problems: list[str] = []

    if cfg.project_profile != "ai26":
        problems.append("Phase 1 Laskin runner is restricted to the ai26 project profile")
    if cfg.allow_cloud_fallback:
        problems.append("cloud fallback must remain disabled for the bounded Laskin run")
    if cfg.discourse_enabled and not cfg.enabled:
        problems.append("discourse cannot be enabled while Phase 1 is disabled")
    if input_path is not None and not input_path.is_file():
        problems.append(f"input JSONL not found: {input_path}")

    ollama_present = importlib.util.find_spec("ollama") is not None
    report["checks"]["ollama_dependency"] = {
        "required": cfg.enabled,
        "installed": ollama_present,
    }
    if cfg.enabled and not ollama_present:
        problems.append("optional dependency missing: install with pip install -e '.[ollama]'")

    if problems:
        report["status"] = "invalid"
        report["problems"] = problems
    return report


def _read_documents(path: Path, limit: int) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ValueError(f"line {line_number} is not a JSON object")
        documents.append(dict(value))
        if len(documents) >= limit:
            break
    return documents


def run_bounded_phase1(
    documents: Iterable[Mapping[str, Any]],
    *,
    provider: Any,
    config: Phase1TextConfig,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> tuple[list[str], dict[str, Any]]:
    """Run at most max_records copied Phase 0 records with per-record isolation."""
    if max_records < 1:
        raise ValueError("max_records must be at least 1")

    outputs: list[str] = []
    failures: list[dict[str, Any]] = []
    processed = 0
    for index, document in enumerate(documents):
        if processed >= max_records:
            break
        processed += 1
        try:
            record = run_phase1_text_record(document, provider=provider, config=config)
            outputs.append(record_to_json(record))
        except Exception as exc:  # noqa: BLE001 - bounded runner must isolate records
            failures.append(
                {
                    "index": index,
                    "source_url": document.get("source_url"),
                    "document_id": document.get("document_id"),
                    "error": type(exc).__name__,
                    "message": str(exc),
                }
            )

    status = {
        "status": "ok" if not failures else "partial",
        "enabled": config.enabled,
        "discourse_enabled": config.discourse_enabled,
        "processed": processed,
        "succeeded": len(outputs),
        "failed": len(failures),
        "failures": failures,
        "phase2_enabled": False,
        "text_only": True,
    }
    return outputs, status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded text-only Phase 1 Laskin runner over copied Phase 0 JSONL"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(os.getenv("LACLAUGPT_PHASE1_INPUT", "data/exports/phase0-laskin-sample.jsonl")),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/exports/phase1-laskin-results.jsonl"),
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=Path("data/logs/phase1-laskin-status.json"),
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=int(os.getenv("LACLAUGPT_PHASE1_MAX_RECORDS", str(DEFAULT_MAX_RECORDS))),
    )
    parser.add_argument("--check", action="store_true", help="preflight only; perform no analysis")
    args = parser.parse_args(argv)

    config = Phase1TextConfig.from_env()
    report = phase1_laskin_preflight(input_path=args.input, config=config)
    if args.check:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "ok" else 2

    if not config.enabled:
        disabled = {
            **report,
            "status": "disabled",
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
        }
        args.status.parent.mkdir(parents=True, exist_ok=True)
        args.status.write_text(json.dumps(disabled, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(disabled, sort_keys=True))
        return 0

    if report["status"] != "ok":
        print(json.dumps(report, indent=2, sort_keys=True), file=sys.stderr)
        return 2

    from .llm.ollama import OllamaProvider

    provider = OllamaProvider(host=os.getenv("LACLAUGPT_LLM_ENDPOINT"))
    documents = _read_documents(args.input, args.max_records)
    outputs, status = run_bounded_phase1(
        documents,
        provider=provider,
        config=config,
        max_records=args.max_records,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(item + "\n" for item in outputs), encoding="utf-8")
    args.status.parent.mkdir(parents=True, exist_ok=True)
    status.update(
        {
            "input": str(args.input),
            "output": str(args.output),
            "max_records": args.max_records,
            "project_profile": config.project_profile,
        }
    )
    args.status.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(status, sort_keys=True))
    return 0 if status["failed"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
