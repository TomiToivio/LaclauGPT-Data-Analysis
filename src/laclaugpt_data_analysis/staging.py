"""Bounded multimodal object staging from object storage (CSC Allas / S3).

Before a multimodal stage can call a model, every object the record references
must exist locally. This module owns that step:

- resolve canonical ``s3://`` (or local) object references from a record;
- reuse a verified local cache hit instead of re-downloading;
- download missing objects into a bounded, private cache area;
- verify size and, where the record supplies one, the SHA-256 checksum;
- report a retriable failure separately from a permanently missing object;
- keep object identity and staging outcome in provenance without credentials;
- prune the cache by age/size so a server disk cannot grow forever;
- never mutate or delete the canonical remote object.

The remote object stays the source of truth. Staging is a local performance and
availability concern, not a research-data operation.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# A record may name its object under any of these canonical locations. The order
# is deliberate: a normalised media reference wins over a raw metadata string.
MEDIA_REFERENCE_FIELDS = ("object_ref",)
OBJECT_REF_FIELDS = (
    "source.raw_metadata.object_ref",
    "source.raw_ref",
    "raw_capture.ref",
)


class ObjectStore(Protocol):
    """The subset of the artifact-store contract staging depends on.

    Only a download method is required. ``stat_ref`` is optional: when a store
    exposes it, staging uses it to pre-check existence and enforce the
    per-object size bound before spending bandwidth.
    """

    def download_to(self, key: str, target: str | Path) -> Path: ...
    def download_ref(self, ref: str, target: str | Path) -> Path: ...
    def stat_ref(self, ref: str) -> dict[str, Any] | None: ...


class StagingError(RuntimeError):
    """Base class for staging failures."""


class ObjectMissingError(StagingError):
    """The referenced object does not exist remotely (permanent)."""


class ObjectCorruptError(StagingError):
    """The object downloaded but failed integrity verification (permanent)."""


class ObjectUnavailableError(StagingError):
    """The object could not be fetched right now (retriable)."""


class StagingPolicy:
    """Bounded cache policy. Defaults are conservative for a shared server.

    Pruning is opt-out rather than opt-in: passing ``max_age_seconds=0`` AND
    ``max_cache_bytes=None`` disables automatic eviction, which is the
    configured Laskin behaviour (retain staged objects until an operator clears
    them). Pruning only ever removes *local* cache entries; the canonical remote
    object is never touched.
    """

    def __init__(
        self,
        *,
        max_cache_bytes: int | None = 8 * 1024**3,
        max_object_bytes: int | None = 512 * 1024**2,
        max_age_seconds: int = 14 * 24 * 3600,
    ) -> None:
        if max_cache_bytes is not None and max_cache_bytes < 1:
            raise ValueError("max_cache_bytes must be positive (or None to disable)")
        if max_object_bytes is not None and max_object_bytes < 1:
            raise ValueError("max_object_bytes must be positive (or None to disable)")
        if max_age_seconds < 0:
            raise ValueError("max_age_seconds must not be negative")
        self.max_cache_bytes = max_cache_bytes
        self.max_object_bytes = max_object_bytes
        self.max_age_seconds = max_age_seconds
        if max_cache_bytes is None and max_age_seconds == 0:
            logger.warning(
                "media staging cache pruning is DISABLED; staged objects are retained "
                "until they are cleared manually"
            )

    @property
    def pruning_enabled(self) -> bool:
        return self.max_cache_bytes is not None or self.max_age_seconds > 0


@dataclass(frozen=True, slots=True)
class StagedObject:
    """Outcome of staging one object reference."""

    ref: str
    path: Path | None
    status: str  # cached | downloaded | missing | corrupt | failed
    byte_size: int | None = None
    checksum: str | None = None
    cache_key: str = ""
    reason: str = ""

    @property
    def local_available(self) -> bool:
        return self.path is not None and self.status in {"cached", "downloaded"}

    @property
    def retriable(self) -> bool:
        return self.status == "failed"

    def provenance(self) -> dict[str, Any]:
        """Credential-free staging record; safe to persist in model provenance."""
        return {
            "object_cache_key": self.cache_key,
            "object_status": self.status,
            "object_byte_size": self.byte_size,
            "object_checksum": self.checksum,
            "object_reason": self.reason,
        }


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dotted(payload: Any, dotted: str) -> Any:
    current = payload
    for part in dotted.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
        if current is None:
            return None
    return current


@dataclass
class StagingReport:
    """Aggregate outcome for one record."""

    staged: list[StagedObject] = field(default_factory=list)
    cache_hits: int = 0
    downloads: int = 0
    pruned_files: int = 0
    pruned_bytes: int = 0

    @property
    def ok(self) -> bool:
        return all(
            item.local_available or item.status == "missing"
            for item in self.staged
        )

    @property
    def local_paths(self) -> list[Path]:
        return [item.path for item in self.staged if item.local_available and item.path]

    def provenance(self) -> dict[str, Any]:
        return {
            "staged_objects": [item.provenance() for item in self.staged],
            "staging_cache_hits": self.cache_hits,
            "staging_downloads": self.downloads,
        }


def object_references(record: Any, *, prefix: str = "") -> list[str]:
    """Collect object references a record declares, in deterministic order."""
    payload = record.model_dump(mode="json") if hasattr(record, "model_dump") else record
    refs: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())

    for dotted in (f"{prefix}{name}" for name in OBJECT_REF_FIELDS):
        add(_dotted(payload, dotted.rstrip(".") if prefix else dotted))

    for ref in (_dotted(payload, "content.media_references") or []):
        if isinstance(ref, dict):
            for name in MEDIA_REFERENCE_FIELDS:
                add(ref.get(name))
    for ref in (_dotted(payload, "content.file_references") or []):
        add(ref)
    for frame in (_dotted(payload, "content.frames") or []):
        if isinstance(frame, dict):
            add(frame.get("media_ref"))

    # Preserve first-seen order while removing duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            unique.append(ref)
    return unique


class MediaStager:
    """Stage referenced objects into a bounded local cache directory."""

    def __init__(
        self,
        store: ObjectStore,
        cache_root: str | Path,
        *,
        policy: StagingPolicy | None = None,
        project_id: str = "",
    ) -> None:
        self.store = store
        self.cache_root = Path(cache_root)
        self.policy = policy or StagingPolicy()
        self.project_id = project_id

    def cache_key(self, ref: str) -> str:
        return _digest(f"{self.project_id}\n{ref}")

    def _target(self, ref: str, *, suffix: str = "") -> Path:
        key = self.cache_key(ref)
        name = Path(ref.split("?", 1)[0]).name or "object.bin"
        if suffix and not name.endswith(suffix):
            name = f"{name}{suffix}"
        return self.cache_root / key[:2] / key / name

    def stage(self, ref: str, *, checksum: str | None = None) -> StagedObject:
        """Stage one object reference, reusing a verified cache hit when possible."""
        key = self.cache_key(ref)
        target = self._target(ref)

        if target.is_file():
            size = target.stat().st_size
            if checksum:
                actual = _sha256_file(target)
                if self._checksum_matches(actual, checksum):
                    return StagedObject(
                        ref=ref,
                        path=target,
                        status="cached",
                        byte_size=size,
                        checksum=actual,
                        cache_key=key,
                    )
                logger.debug("cached object failed checksum verification; refetching")
                target.unlink(missing_ok=True)
            else:
                return StagedObject(
                    ref=ref,
                    path=target,
                    status="cached",
                    byte_size=size,
                    cache_key=key,
                )

        # Confirm the remote object exists before spending bandwidth, and use the
        # reported size to enforce the per-object bound. Stores that do not expose
        # ``stat_ref`` simply skip this pre-flight check.
        info: dict[str, Any] | None = None
        stat = getattr(self.store, "stat_ref", None)
        if stat is not None:
            try:
                info = stat(ref)
            except ObjectMissingError:
                return StagedObject(ref=ref, path=None, status="missing", cache_key=key,
                                    reason="object_not_found")
            except Exception as exc:  # noqa: BLE001 - classification is the point
                return StagedObject(
                    ref=ref,
                    path=None,
                    status="failed",
                    cache_key=key,
                    reason=f"stat_failed:{type(exc).__name__}",
                )

        if info is None and stat is not None:
            return StagedObject(ref=ref, path=None, status="missing", cache_key=key,
                                reason="object_not_found")

        remote_size = info.get("byte_size") if info else None
        limit = self.policy.max_object_bytes
        if remote_size is not None and limit is not None and remote_size > limit:
            return StagedObject(
                ref=ref,
                path=None,
                status="corrupt",
                byte_size=remote_size,
                cache_key=key,
                reason="object_exceeds_max_object_bytes",
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".part")
        try:
            self._download(ref, temp)
        except ObjectMissingError:
            temp.unlink(missing_ok=True)
            return StagedObject(ref=ref, path=None, status="missing", cache_key=key,
                                reason="object_not_found")
        except Exception as exc:  # noqa: BLE001
            temp.unlink(missing_ok=True)
            return StagedObject(
                ref=ref,
                path=None,
                status="failed",
                cache_key=key,
                reason=f"download_failed:{type(exc).__name__}",
            )

        if not temp.is_file():
            return StagedObject(ref=ref, path=None, status="failed", cache_key=key,
                                reason="download_produced_no_file")

        actual_size = temp.stat().st_size
        if actual_size == 0 or (limit is not None and actual_size > limit):
            temp.unlink(missing_ok=True)
            return StagedObject(
                ref=ref,
                path=None,
                status="corrupt",
                byte_size=actual_size,
                cache_key=key,
                reason="object_size_invalid",
            )
        if remote_size is not None and actual_size != remote_size:
            temp.unlink(missing_ok=True)
            return StagedObject(
                ref=ref,
                path=None,
                status="corrupt",
                byte_size=actual_size,
                cache_key=key,
                reason="object_size_mismatch",
            )

        actual = _sha256_file(temp)
        if checksum and not self._checksum_matches(actual, checksum):
            temp.unlink(missing_ok=True)
            return StagedObject(
                ref=ref,
                path=None,
                status="corrupt",
                byte_size=actual_size,
                checksum=actual,
                cache_key=key,
                reason="object_checksum_mismatch",
            )

        temp.replace(target)
        return StagedObject(
            ref=ref,
            path=target,
            status="downloaded",
            byte_size=actual_size,
            checksum=actual,
            cache_key=key,
        )

    def _download(self, ref: str, target: Path) -> Path:
        """Download via whichever contract the store exposes.

        ``S3ArtifactStore`` provides ``download_ref`` (validating the bucket);
        ``LocalArtifactStore`` provides ``download_to``. Supporting both keeps
        staging usable against a local fake in tests and against Allas in
        production without duplicating the store's validation logic.
        """
        download_ref = getattr(self.store, "download_ref", None)
        if download_ref is not None:
            return download_ref(ref, target)
        return self.store.download_to(ref, target)

    @staticmethod
    def _checksum_matches(actual: str, expected: str) -> bool:
        return actual.casefold() == str(expected).strip().casefold().removeprefix("sha256:")

    def stage_record(self, record: Any, *, prefix: str = "") -> StagingReport:
        """Stage every object a record references, then apply the cache policy."""
        report = StagingReport()
        checksums = self._record_checksums(record)
        for ref in object_references(record, prefix=prefix):
            item = self.stage(ref, checksum=checksums.get(ref))
            report.staged.append(item)
            if item.status == "cached":
                report.cache_hits += 1
            elif item.status == "downloaded":
                report.downloads += 1
        pruned_files, pruned_bytes = self.prune_cache()
        report.pruned_files = pruned_files
        report.pruned_bytes = pruned_bytes
        return report

    def _record_checksums(self, record: Any) -> dict[str, str]:
        payload = record.model_dump(mode="json") if hasattr(record, "model_dump") else record
        found: dict[str, str] = {}
        raw_ref = _dotted(payload, "source.raw_metadata.object_ref")
        raw_checksum = _dotted(payload, "source.raw_metadata.sha256")
        if isinstance(raw_ref, str) and isinstance(raw_checksum, str):
            found[raw_ref] = raw_checksum
        for ref in (_dotted(payload, "content.media_references") or []):
            if isinstance(ref, dict):
                object_ref = ref.get("object_ref")
                checksum = ref.get("checksum")
                if isinstance(object_ref, str) and isinstance(checksum, str) and checksum:
                    found[object_ref] = checksum
        return found

    def prune_cache(self) -> tuple[int, int]:
        """Drop aged/excess cache entries. Never touches the remote object.

        Returns ``(files_removed, bytes_removed)``. When the policy disables
        pruning (no size budget and no age limit) this is a no-op.
        """
        if not self.policy.pruning_enabled:
            return 0, 0
        if not self.cache_root.exists():
            return 0, 0
        entries: list[tuple[float, Path]] = []
        for path in self.cache_root.rglob("*"):
            if path.is_file() and not path.name.endswith(".part"):
                try:
                    entries.append((path.stat().st_mtime, path))
                except OSError:  # pragma: no cover - racing filesystem
                    continue

        removed = 0
        removed_bytes = 0
        now = time.time()

        if self.policy.max_age_seconds:
            for mtime, path in list(entries):
                if now - mtime <= self.policy.max_age_seconds:
                    continue
                try:
                    size = path.stat().st_size
                    path.unlink()
                    removed += 1
                    removed_bytes += size
                    entries.remove((mtime, path))
                except OSError:  # pragma: no cover
                    continue

        if self.policy.max_cache_bytes is not None:
            total = sum(path.stat().st_size for _, path in entries if path.exists())
            if total > self.policy.max_cache_bytes:
                for _, path in sorted(entries):
                    if total <= self.policy.max_cache_bytes:
                        break
                    try:
                        size = path.stat().st_size
                        path.unlink()
                        total -= size
                        removed += 1
                        removed_bytes += size
                    except OSError:  # pragma: no cover
                        continue

        self._remove_empty_dirs()
        return removed, removed_bytes

    def _remove_empty_dirs(self) -> None:
        for path in sorted(self.cache_root.rglob("*"), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    continue

    def clear(self) -> None:
        """Remove the whole local cache. Safe: the remote object is untouched."""
        if self.cache_root.exists():
            shutil.rmtree(self.cache_root, ignore_errors=True)
