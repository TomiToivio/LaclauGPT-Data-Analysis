from __future__ import annotations

import csv
import json
from pathlib import Path

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.reprocessing import (
    AtomicCheckpointWriter,
    CheckpointConfig,
    ReprocessingConfig,
    load_manifest,
    sha256_file,
)


def test_reprocessing_config_is_project_neutral():
    config = ReprocessingConfig(
        project_id="synthetic_restricted",
        manifest="data/config/private/manifest.jsonl",
        codebook="data/config/private/codebook.yaml",
    )
    assert config.project_profile == "generic"
    assert config.checkpoint.every_records == 25
    assert config.lease_ttl_seconds == 7200


def test_load_manifest_preserves_canonical_and_legacy_fields(tmp_path: Path):
    record = CanonicalRecord(source_url="urn:test:1", legacy={"old_frame_label": "x"})
    record.intermediate.asr.append({"text": "hei maailma", "provider": "synthetic"})
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n", encoding="utf-8")

    loaded = load_manifest(manifest)

    assert [item.source_url for item in loaded] == ["urn:test:1"]
    assert loaded[0].legacy["old_frame_label"] == "x"
    assert loaded[0].intermediate.asr[0]["text"] == "hei maailma"


def test_atomic_checkpoint_round_trip_contains_non_lossy_json(tmp_path: Path):
    record = CanonicalRecord(source_url="urn:test:unicode", legacy={"fi": "ääkkönen", "emoji": "🤖"})
    record.analysis.status = "analyzed"
    record.analysis.summary = "Tutkijan yhteenveto"
    writer = AtomicCheckpointWriter(tmp_path, CheckpointConfig(every_records=1, every_seconds=30, retain=2))

    snapshot = writer.write([record], completed_count=1)

    assert snapshot is not None and snapshot.exists()
    assert (tmp_path / "latest.csv").exists()
    with (tmp_path / "latest.csv").open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["source_url"] == "urn:test:unicode"
    assert row["human_summary"] == "Tutkijan yhteenveto"
    payload = json.loads(row["canonical_json"])
    assert payload["legacy"]["fi"] == "ääkkönen"
    assert payload["legacy"]["emoji"] == "🤖"


def test_atomic_checkpoint_retention(tmp_path: Path):
    writer = AtomicCheckpointWriter(tmp_path, CheckpointConfig(every_records=1, every_seconds=30, retain=2))
    record = CanonicalRecord(source_url="urn:test:retention")
    for count in range(1, 5):
        writer._last_time = 0
        writer.write([record], completed_count=count, force=True)
    assert len(list(tmp_path.glob("checkpoint-*.csv"))) <= 2


def test_sha256_file(tmp_path: Path):
    path = tmp_path / "object.bin"
    path.write_bytes(b"restricted-project-test")
    assert sha256_file(path) == "f5e6da3281185879d14af7a4ded51d77fcfae312394edff3bd60c1bb1dba7e85"
