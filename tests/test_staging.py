"""Offline tests for bounded multimodal object staging from Allas/S3.

CI must never require CSC credentials, so every test uses a fake object store
that implements the same ``download_ref``/``stat_ref`` contract as
``S3ArtifactStore``.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.staging import (
    MediaStager,
    ObjectMissingError,
    StagingPolicy,
    object_references,
)


class FakeObjectStore:
    """Minimal S3-shaped fake with controllable failure modes."""

    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = dict(objects or {})
        self.downloads: list[str] = []
        self.stat_calls: list[str] = []
        self.stat_error: Exception | None = None
        self.download_error: Exception | None = None
        # When set, the fake reports this size for every object regardless of
        # its real length, simulating an object that changed remotely.
        self.reported_size: int | None = None

    def _key(self, ref: str) -> str:
        assert ref.startswith("s3://test-bucket/"), ref
        # The fake keys objects by the full reference so tests read naturally.
        return ref

    def stat_ref(self, ref: str):
        self.stat_calls.append(ref)
        if self.stat_error is not None:
            raise self.stat_error
        key = self._key(ref)
        if key not in self.objects:
            return None
        return {
            "byte_size": self.reported_size
            if self.reported_size is not None
            else len(self.objects[key]),
            "etag": hashlib.md5(self.objects[key]).hexdigest(),  # noqa: S324 - fake ETag
            "checksum": None,
        }

    def download_ref(self, ref: str, target: str | Path) -> Path:
        self.downloads.append(ref)
        if self.download_error is not None:
            raise self.download_error
        key = self._key(ref)
        if key not in self.objects:
            raise ObjectMissingError(ref)
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.objects[key])
        return destination


def _stager(tmp_path: Path, store: FakeObjectStore, **policy) -> MediaStager:
    return MediaStager(
        store,
        tmp_path / "cache",
        policy=StagingPolicy(**policy) if policy else StagingPolicy(),
        project_id="ai26",
    )


def _record(*, media_ref: str | None = None, frame_ref: str | None = None,
            checksum: str | None = None) -> CanonicalRecord:
    payload: dict = {"source_url": "https://example.invalid/item/1", "content": {}}
    if media_ref:
        ref: dict = {"kind": "image", "url": "https://example.invalid/a.png",
                     "object_ref": media_ref}
        if checksum:
            ref["checksum"] = checksum
        payload["content"]["media_references"] = [ref]
    if frame_ref:
        payload["content"]["frames"] = [
            {"id": "f0", "timestamp_seconds": 0.0, "media_ref": frame_ref}
        ]
    return CanonicalRecord.model_validate(payload)


REF = "s3://test-bucket/projects/ai26/runs/r/media/frame0.png"
PAYLOAD = b"\x89PNG\r\n\x1a\nsynthetic-frame-bytes"


def test_object_references_collects_canonical_locations_deterministically() -> None:
    record = _record(media_ref=REF, frame_ref="s3://test-bucket/frames/f1.png")
    refs = object_references(record)
    assert refs == [REF, "s3://test-bucket/frames/f1.png"]


def test_downloads_missing_object_and_verifies_size(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store)

    item = stager.stage(REF)

    assert item.status == "downloaded"
    assert item.local_available
    assert item.path is not None and item.path.read_bytes() == PAYLOAD
    assert item.byte_size == len(PAYLOAD)
    assert store.downloads == [REF]
    assert item.provenance()["object_status"] == "downloaded"


def test_cache_hit_avoids_redundant_download(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store)

    first = stager.stage(REF)
    second = stager.stage(REF)

    assert first.status == "downloaded"
    assert second.status == "cached"
    assert store.downloads == [REF]  # only once
    assert second.path == first.path


def test_cached_object_with_matching_checksum_is_reused(tmp_path: Path) -> None:
    checksum = hashlib.sha256(PAYLOAD).hexdigest()
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store)

    stager.stage(REF, checksum=checksum)
    second = stager.stage(REF, checksum=f"sha256:{checksum}")

    assert second.status == "cached"
    assert store.downloads == [REF]


def test_corrupt_cached_object_is_refetched(tmp_path: Path) -> None:
    checksum = hashlib.sha256(PAYLOAD).hexdigest()
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store)

    stager.stage(REF, checksum=checksum)
    cached = stager._target(REF)
    cached.write_bytes(b"tampered")
    second = stager.stage(REF, checksum=checksum)

    assert second.status == "downloaded"
    assert second.path is not None and second.path.read_bytes() == PAYLOAD
    assert store.downloads == [REF, REF]


def test_missing_object_is_permanent_not_retriable(tmp_path: Path) -> None:
    store = FakeObjectStore({})
    stager = _stager(tmp_path, store)

    item = stager.stage(REF)

    assert item.status == "missing"
    assert not item.local_available
    assert not item.retriable
    assert item.provenance()["object_reason"] == "object_not_found"
    assert store.downloads == []  # never attempted


def test_transport_failure_is_retriable(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    store.stat_error = TimeoutError("connection reset")
    stager = _stager(tmp_path, store)

    item = stager.stage(REF)

    assert item.status == "failed"
    assert item.retriable
    assert "stat_failed" in item.provenance()["object_reason"]


def test_download_failure_is_retriable_and_leaves_no_partial_file(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    store.download_error = ConnectionError("network down")
    stager = _stager(tmp_path, store)

    item = stager.stage(REF)

    assert item.status == "failed"
    assert item.retriable
    target = stager._target(REF)
    assert not target.exists()
    assert not list(stager.cache_root.rglob("*.part"))


def test_size_mismatch_is_corrupt_not_silently_accepted(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    store.reported_size = len(PAYLOAD) + 999
    stager = _stager(tmp_path, store)

    item = stager.stage(REF)

    assert item.status == "corrupt"
    assert item.provenance()["object_reason"] == "object_size_mismatch"


def test_checksum_mismatch_is_corrupt(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store)

    item = stager.stage(REF, checksum="deadbeef" * 8)

    assert item.status == "corrupt"
    assert item.provenance()["object_reason"] == "object_checksum_mismatch"


def test_oversized_object_is_refused_before_download(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store, max_object_bytes=4)

    item = stager.stage(REF)

    assert item.status == "corrupt"
    assert item.provenance()["object_reason"] == "object_exceeds_max_object_bytes"
    assert store.downloads == []


def test_stage_record_reports_aggregate_and_points_frames_at_local_files(
    tmp_path: Path,
) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store)
    record = _record(media_ref=REF, frame_ref=REF)

    report = stager.stage_record(record)

    assert report.downloads == 1
    assert report.cache_hits == 0
    assert report.ok
    assert len(report.local_paths) == 1
    provenance = report.provenance()
    assert provenance["staging_downloads"] == 1
    assert provenance["staged_objects"][0]["object_status"] == "downloaded"


def test_stage_record_is_ok_when_a_referenced_object_is_permanently_missing(
    tmp_path: Path,
) -> None:
    """A missing object must not abort a text-capable record forever."""
    store = FakeObjectStore({})
    stager = _stager(tmp_path, store)

    report = stager.stage_record(_record(media_ref=REF))

    assert report.ok
    assert report.local_paths == []


def test_prune_removes_entries_over_the_size_budget(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store, max_cache_bytes=8)
    stager.stage(REF)
    assert stager._target(REF).exists()

    removed, removed_bytes = stager.prune_cache()

    assert removed >= 1
    assert removed_bytes >= len(PAYLOAD)
    assert not stager._target(REF).exists()


def test_prune_removes_entries_older_than_max_age(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store, max_age_seconds=1)
    stager.stage(REF)
    target = stager._target(REF)
    old = target.stat().st_mtime - 3600
    import os

    os.utime(target, (old, old))

    removed, _ = stager.prune_cache()

    assert removed == 1
    assert not target.exists()


def test_clear_removes_local_cache_only(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store)
    stager.stage(REF)

    stager.clear()

    assert not stager.cache_root.exists()
    # The canonical remote object is untouched.
    assert REF in store.objects


def test_policy_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError):
        StagingPolicy(max_cache_bytes=0)
    with pytest.raises(ValueError):
        StagingPolicy(max_object_bytes=0)
    with pytest.raises(ValueError):
        StagingPolicy(max_age_seconds=-1)


def test_pruning_can_be_disabled_explicitly(tmp_path: Path) -> None:
    """Laskin retains staged objects until an operator clears them."""
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(
        tmp_path, store, max_cache_bytes=None, max_age_seconds=0
    )
    assert stager.policy.pruning_enabled is False

    stager.stage(REF)
    target = stager._target(REF)
    assert target.exists()

    removed, removed_bytes = stager.prune_cache()

    assert (removed, removed_bytes) == (0, 0)
    assert target.exists()  # nothing evicted while pruning is disabled


def test_disabled_pruning_survives_stage_record(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store, max_cache_bytes=None, max_age_seconds=0)

    report = stager.stage_record(_record(media_ref=REF))

    assert report.pruned_files == 0
    assert stager._target(REF).exists()


def test_oversized_object_is_allowed_when_object_bound_removed(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store, max_object_bytes=None, max_age_seconds=0)

    item = stager.stage(REF)

    assert item.status == "downloaded"
    assert item.byte_size == len(PAYLOAD)


def test_provenance_never_carries_credentials_or_absolute_paths(tmp_path: Path) -> None:
    store = FakeObjectStore({REF: PAYLOAD})
    stager = _stager(tmp_path, store)

    payload = stager.stage(REF).provenance()

    rendered = str(payload)
    assert "s3://" not in rendered
    assert "AKIA" not in rendered
    assert str(tmp_path) not in rendered
    assert set(payload) == {
        "object_cache_key",
        "object_status",
        "object_byte_size",
        "object_checksum",
        "object_reason",
    }
