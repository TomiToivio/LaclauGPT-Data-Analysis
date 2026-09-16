"""Generic restricted-project reprocessing for CSC Roihu and similar batch hosts.

Project manifests, source identifiers, codebooks, credentials and paths stay private.
The public engine supplies orchestration, Allas/S3 staging, checkpointing, durable state,
Redis best-effort leases and canonical-pipeline integration.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, Field

from .canonical import CanonicalRecord
from .canonical_pipeline import PipelineContext, run_canonical_pipeline
from .codebooks import load_codebook
from .config import Settings, load_settings
from .llm.ollama import OllamaProvider
from .storage import artifact_store, cache, record_store


class CheckpointConfig(BaseModel):
    every_records: int = Field(default=25, ge=1)
    every_seconds: int = Field(default=600, ge=30)
    retain: int = Field(default=8, ge=1)


class ReprocessingConfig(BaseModel):
    project_id: str
    project_profile: str = "generic"
    manifest: str
    codebook: str
    model: str = "auto"
    prompt_version: str = "restricted-reprocessing-v1"
    source_object_field: str = "source.raw_metadata.object_ref"
    checksum_field: str = "source.raw_metadata.sha256"
    preprocessor_hook: str | None = None
    lease_ttl_seconds: int = Field(default=7200, ge=60)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)
    archive_checkpoints: bool = True
    cleanup_staged_media: bool = True


def load_reprocessing_config(path: str | Path) -> ReprocessingConfig:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return ReprocessingConfig.model_validate(payload)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dotted(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _load_hook(
    spec: str | None,
) -> Callable[[CanonicalRecord], dict[str, Any] | None] | None:
    if not spec:
        return None
    module_name, sep, function_name = spec.partition(":")
    if not sep:
        raise ValueError("preprocessor_hook must use module:function syntax")
    function = getattr(importlib.import_module(module_name), function_name)
    if not callable(function):
        raise TypeError(f"configured preprocessor hook is not callable: {spec}")
    return function


def load_manifest(path: str | Path) -> list[CanonicalRecord]:
    source = Path(path)
    records: list[CanonicalRecord] = []
    if source.suffix.casefold() in {".jsonl", ".ndjson"}:
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(CanonicalRecord.model_validate(json.loads(line)))
        return records
    if source.suffix.casefold() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("records", [])
        return [CanonicalRecord.model_validate(row) for row in rows]
    raise ValueError("restricted reprocessing manifests must be canonical JSON or JSONL")


class AtomicCheckpointWriter:
    """Write non-lossy atomic CSV snapshots with deterministic nested JSON."""

    def __init__(self, root: str | Path, config: CheckpointConfig):
        self.root = Path(root)
        self.config = config
        self.root.mkdir(parents=True, exist_ok=True)
        self._last_time = time.monotonic()
        self._last_count = 0

    @staticmethod
    def flatten(record: CanonicalRecord) -> dict[str, str]:
        payload = record.model_dump(mode="json")
        return {
            "source_url": record.source_url,
            "analysis_status": str(record.analysis.status or ""),
            "human_summary": str(record.analysis.summary or ""),
            "canonical_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "legacy_json": json.dumps(
                payload.get("legacy", {}), ensure_ascii=False, sort_keys=True
            ),
            "intermediate_json": json.dumps(
                payload.get("intermediate", {}), ensure_ascii=False, sort_keys=True
            ),
            "provenance_json": json.dumps(
                payload.get("provenance", []), ensure_ascii=False, sort_keys=True
            ),
        }

    def due(self, completed_count: int) -> bool:
        count_due = completed_count - self._last_count >= self.config.every_records
        time_due = time.monotonic() - self._last_time >= self.config.every_seconds
        return count_due or time_due

    def write(
        self,
        records: list[CanonicalRecord],
        *,
        completed_count: int,
        force: bool = False,
    ) -> Path | None:
        if not force and not self.due(completed_count):
            return None
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        snapshot = self.root / f"checkpoint-{stamp}.csv"
        latest = self.root / "latest.csv"
        rows = [self.flatten(record) for record in records]
        fields = (
            list(rows[0])
            if rows
            else [
                "source_url",
                "analysis_status",
                "human_summary",
                "canonical_json",
                "legacy_json",
                "intermediate_json",
                "provenance_json",
            ]
        )
        for target in (snapshot, latest):
            fd, temp_name = tempfile.mkstemp(
                prefix=target.name + ".", suffix=".tmp", dir=target.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
                os.replace(temp_name, target)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        snapshots = sorted(self.root.glob("checkpoint-*.csv"), reverse=True)
        for stale in snapshots[self.config.retain :]:
            stale.unlink(missing_ok=True)
        self._last_count = completed_count
        self._last_time = time.monotonic()
        return snapshot


@dataclass
class RunSummary:
    project_id: str
    processed: int = 0
    skipped: int = 0
    failed: int = 0


class ReprocessingEngine:
    def __init__(self, settings: Settings, config: ReprocessingConfig):
        if settings.project_id != config.project_id:
            raise ValueError("runtime project_id must match restricted reprocessing config")
        self.settings = settings
        self.config = config
        self.records = record_store(settings, "analysis")
        self.objects = artifact_store(settings)
        self.cache = cache(settings)
        self.codebook = load_codebook(config.codebook)
        self.preprocessor = _load_hook(config.preprocessor_hook)
        self.provider = OllamaProvider(host=settings.llm_endpoint)
        self.checkpoints = AtomicCheckpointWriter(
            settings.data_path("csv", config.project_id, "checkpoints"),
            config.checkpoint,
        )

    @staticmethod
    def _digest(source_url: str) -> str:
        return hashlib.sha256(source_url.encode("utf-8")).hexdigest()

    def _lease_key(self, source_url: str) -> str:
        return "reprocess:lease:" + self._digest(source_url)

    def _lease_active(self, source_url: str) -> bool:
        raw = self.cache.get(self._lease_key(source_url))
        if not raw:
            return False
        try:
            return time.time() - float(raw) < self.config.lease_ttl_seconds
        except (TypeError, ValueError):
            return False

    def _completed(self, source_url: str) -> bool:
        marker = self.cache.get("reprocess:done:" + self._digest(source_url))
        if marker:
            return True
        for row in self.records.read():
            analysis = row.get("analysis", {})
            if row.get("source_url") == source_url and analysis.get("status") == "analyzed":
                return True
        return False

    def _stage_object(self, record: CanonicalRecord) -> Path | None:
        payload = record.model_dump(mode="json")
        ref = _dotted(payload, self.config.source_object_field)
        if not ref:
            return None
        target = self.settings.data_path(
            "tmp",
            self.config.project_id,
            self._digest(record.source_url)[:16],
            Path(str(ref)).name or "source.bin",
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(self.objects, "download_ref") and str(ref).startswith("s3://"):
            self.objects.download_ref(str(ref), target)
        else:
            self.objects.download_to(str(ref), target)
        expected = _dotted(payload, self.config.checksum_field)
        if expected and sha256_file(target).casefold() != str(expected).casefold():
            raise ValueError("staged object checksum mismatch")
        # Temporary path is exposed only to the private preprocessing hook and is
        # removed before durable persistence so machine-specific scratch paths do
        # not become canonical research metadata.
        record.source.raw_metadata["staged_path"] = str(target)
        return target

    def _archive_checkpoint(self, snapshot: Path | None) -> None:
        if snapshot is None or not self.config.archive_checkpoints:
            return
        self.objects.upload_file(
            f"restricted-checkpoints/{self.config.project_id}/{snapshot.name}", snapshot
        )

    def run(
        self,
        records: list[CanonicalRecord],
        *,
        force: bool = False,
        start: int = 0,
        stop: int | None = None,
    ) -> RunSummary:
        summary = RunSummary(project_id=self.config.project_id)
        selected = records[start:stop]
        for record in selected:
            if not force and self._completed(record.source_url):
                summary.skipped += 1
                continue
            if not force and self._lease_active(record.source_url):
                summary.skipped += 1
                continue
            self.cache.set(self._lease_key(record.source_url), str(time.time()))
            staged: Path | None = None
            try:
                staged = self._stage_object(record)
                processed = run_canonical_pipeline(
                    record,
                    provider=self.provider,
                    context=PipelineContext(project_context=self.config.project_id),
                    codebook_entries=self.codebook.entries,
                    preprocessor=self.preprocessor,
                    model=self.config.model,
                    project_profile=self.config.project_profile,
                    prompt_version=self.config.prompt_version,
                    allow_cloud_fallback=self.settings.cloud_allowed,
                )
                processed.source.raw_metadata.pop("staged_path", None)
                processed.source.raw_metadata.setdefault("reprocessing", {}).update(
                    {
                        "project_id": self.config.project_id,
                        "codebook": self.codebook.provenance_snapshot(),
                        "prompt_version": self.config.prompt_version,
                        "model": self.config.model,
                        "machine": self.settings.machine,
                        "execution": self.settings.execution,
                        "slurm_job_id": os.getenv("SLURM_JOB_ID", ""),
                    }
                )
                self.records.write([processed.model_dump(mode="json")])
                self.cache.set("reprocess:done:" + self._digest(record.source_url), "1")
                summary.processed += 1
                self._archive_checkpoint(
                    self.checkpoints.write(
                        selected,
                        completed_count=summary.processed + summary.failed,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                record.source.raw_metadata.pop("staged_path", None)
                record.source.raw_metadata.setdefault("reprocessing", {})[
                    "last_error"
                ] = f"{type(exc).__name__}: {exc}"
                self.records.write([record.model_dump(mode="json")])
                summary.failed += 1
            finally:
                if staged and self.config.cleanup_staged_media:
                    staged.unlink(missing_ok=True)
        self._archive_checkpoint(
            self.checkpoints.write(
                selected,
                completed_count=summary.processed + summary.failed,
                force=True,
            )
        )
        return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="laclaugpt-reprocess")
    parser.add_argument("--config", required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    config = load_reprocessing_config(args.config)
    settings = load_settings()
    records = load_manifest(config.manifest)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "project_id": config.project_id,
                    "records": len(records),
                    "start": args.start,
                    "stop": args.stop,
                    "codebook_sha256": load_codebook(config.codebook).fingerprint(),
                },
                indent=2,
            )
        )
        return 0
    result = ReprocessingEngine(settings, config).run(
        records, force=args.force, start=args.start, stop=args.stop
    )
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
