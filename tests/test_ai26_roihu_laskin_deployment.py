from pathlib import Path

import pytest

from laclaugpt_data_analysis.storage import S3ArtifactStore

ROOT = Path(__file__).resolve().parents[1]


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.downloads = []

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.objects[(Bucket, Key)] = (bytes(Body), ContentType)

    def get_object(self, *, Bucket, Key):
        data = self.objects[(Bucket, Key)][0]

        class Body:
            def read(self_nonlocal):
                return data

        return {"Body": Body()}

    def upload_file(self, source, bucket, key):
        self.objects[(bucket, key)] = (Path(source).read_bytes(), "application/octet-stream")

    def download_file(self, bucket, key, target):
        Path(target).write_bytes(self.objects[(bucket, key)][0])
        self.downloads.append((bucket, key, target))


def test_laskin_wrapper_is_bounded_cron_safe():
    script = (ROOT / "scripts/run_ai26_laskin_analysis.sh").read_text(encoding="utf-8")
    assert "flock -n" in script
    assert "--max-tasks" in script
    assert "--reclaim-idle-ms" in script
    assert "--worker-id \"laskin-cron-" in script
    assert "LACLAUGPT_OBJECT_BACKEND=s3" in script
    assert "laclaugpt-analysis-worker" in script


def test_roihu_template_uses_shared_distributed_worker():
    script = (ROOT / "scripts/roihu/ai26_worker.sbatch.example").read_text(encoding="utf-8")
    assert "LACLAUGPT_MACHINE=roihu" in script
    assert "LACLAUGPT_EXECUTION=slurm" in script
    assert "LACLAUGPT_OBJECT_BACKEND=s3" in script
    assert "SLURM_JOB_ID" in script
    assert "--reclaim-idle-ms" in script
    assert "laclaugpt-analysis-worker" in script


def test_public_profiles_share_ai26_distributed_namespace():
    roihu = (ROOT / "deployment/ai26.roihu.env.example").read_text(encoding="utf-8")
    laskin = (ROOT / "deployment/ai26.laskin.env.example").read_text(encoding="utf-8")
    for required in (
        "LACLAUGPT_PROJECT_ID=ai26",
        "LACLAUGPT_DATA_BACKEND=mongodb",
        "LACLAUGPT_CACHE_BACKEND=redis",
        "LACLAUGPT_OBJECT_BACKEND=s3",
        "LACLAUGPT_S3_PREFIX_ROOT=projects",
    ):
        assert required in roihu
        assert required in laskin
    assert "LACLAUGPT_MACHINE=roihu" in roihu
    # #79 opened the deployment identifier: the Laskin profile records the real
    # machine name instead of the former generic class value. This assertion
    # failed on unmodified main; kept aligned here while this file is touched.
    assert "LACLAUGPT_MACHINE=laskin" in laskin


def test_s3_artifact_store_stages_binary_files(tmp_path):
    store = object.__new__(S3ArtifactStore)
    store.bucket = "bucket"
    store.prefix = "projects/ai26/analysis"
    store.client = FakeS3Client()

    source = tmp_path / "source.bin"
    source.write_bytes(b"abc123")
    ref = store.upload_file("runs/run-1/result.bin", source)
    assert ref == "s3://bucket/projects/ai26/analysis/runs/run-1/result.bin"

    target = tmp_path / "target.bin"
    store.download_ref(ref, target)
    assert target.read_bytes() == b"abc123"

    ref2 = store.put_bytes("runs/run-1/raw.bin", b"xyz")
    assert ref2.endswith("/projects/ai26/analysis/runs/run-1/raw.bin")
    assert store.get_bytes("runs/run-1/raw.bin") == b"xyz"


def test_s3_artifact_store_rejects_foreign_bucket(tmp_path):
    store = object.__new__(S3ArtifactStore)
    store.bucket = "bucket"
    store.prefix = "projects/ai26/analysis"
    store.client = FakeS3Client()
    with pytest.raises(ValueError):
        store.download_ref("s3://other-bucket/file.bin", tmp_path / "x.bin")
