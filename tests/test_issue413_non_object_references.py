"""A capture-side path in `source.raw_ref` is not an object, and must not be staged (#413).

An AI26 X record carries two references: a producer-side relative path such as
`raw/x/20261026/capture-….ndjson`, and the real `s3://…` object. The stager collected both, the S3
store refused the first by construction, and — before #415 — classified that refusal as retriable, so
every X record aborted in staging before a single model call.

#415 made the refusal permanent. This closes the other half: the stager now asks the store whether it
can address a reference at all, skips the ones it cannot, and records them as skipped rather than
attempting a download that can only fail. The record's real object is still staged, which is what lets
the analysis proceed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laclaugpt_data_analysis.staging import MediaStager, StagingPolicy, object_references  # noqa: E402


class RecordingStore:
    """An object store that only addresses `s3://bucket/` keys, like S3ArtifactStore."""

    def __init__(self):
        self.downloads = []

    def addressable(self, ref: str) -> bool:
        return str(ref).startswith("s3://LaclauGPT-AI26/")

    def download_to(self, key: str, target):
        self.downloads.append(key)
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{\"ok\": true}\n")
        return path

    def exists(self, key: str) -> bool:
        return True


def _record():
    return {
        "source": {
            "raw_ref": "raw/x/20261026/capture-20261026T145437Z-00005049.ndjson",
            "created_at": "2026-10-26T14:54:37Z",
        },
        "raw_capture": {
            "ref": "s3://LaclauGPT-AI26/projects/ai26/runs/ai26-distributed-001/raw/58432e.json",
        },
    }


def test_both_references_are_collected_before_the_store_is_consulted():
    refs = object_references(_record())
    assert len(refs) == 2


def test_the_non_object_reference_is_skipped_not_attempted(tmp_path):
    store = RecordingStore()
    stager = MediaStager(store, tmp_path, policy=StagingPolicy())

    report = stager.stage_record(_record())

    # exactly one download: the real object
    assert store.downloads == [
        "s3://LaclauGPT-AI26/projects/ai26/runs/ai26-distributed-001/raw/58432e.json"
    ]
    skipped = [item for item in report.staged if item.ref.startswith("raw/x/")]
    assert len(skipped) == 1
    assert skipped[0].status == "not_an_object"
    assert skipped[0].local_available is False
    assert skipped[0].retriable is False
    assert "not addressable" in skipped[0].reason


def test_nothing_in_the_report_is_retriable_so_the_task_does_not_abort(tmp_path):
    stager = MediaStager(RecordingStore(), tmp_path, policy=StagingPolicy())
    report = stager.stage_record(_record())
    assert [item for item in report.staged if item.retriable] == []


def test_a_store_without_the_capability_still_works(tmp_path):
    """The capability is duck-typed: a store that does not implement it keeps the old behaviour."""

    class PlainStore:
        def download_to(self, key, target):
            path = Path(target)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
            return path

    stager = MediaStager(PlainStore(), tmp_path, policy=StagingPolicy())
    report = stager.stage_record({"raw_capture": {"ref": "s3://bucket/key.json"}})
    assert len(report.staged) == 1
