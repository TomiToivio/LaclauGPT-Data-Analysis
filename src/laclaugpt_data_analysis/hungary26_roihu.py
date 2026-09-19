"""Local SQLite/CSV Hungary26 multimodal runner for CSC Roihu.

This module is intentionally separate from the hand-maintained Phase 0 core in
``laclaugpt/``. It uses local files + SQLite for resumability, materializes
Allas media before inference, extracts bounded keyframes with ffmpeg, attaches
actual image bytes/paths to local Ollama, and exports researcher-readable CSVs.

MongoDB and Redis are deliberately not part of this runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .hungary26 import WorkbookRecord, deterministic_pilot, load_hungary26_workbook
from .staging import MediaStager, StagingPolicy
from .storage import S3ArtifactStore

DEFAULT_MODEL = "gemma4:12b"
DEFAULT_PRIVATE_ROOT = Path("/scratch/project_2009497/LaclauGPT-Private/analysis/hungary26")
STAGES = ("download", "frames", "vision", "summary", "discourse")


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_fingerprint(*, record: WorkbookRecord, model: str, prompt_version: str,
                        codebook_hash: str, config_hash: str) -> str:
    return sha256_text(stable_json({
        "source": record.exact_fingerprint,
        "media_ref": record.media_ref,
        "model": model,
        "prompt_version": prompt_version,
        "codebook_hash": codebook_hash,
        "config_hash": config_hash,
    }))


@dataclass(frozen=True)
class StageResult:
    document_id: str
    stage: str
    fingerprint: str
    status: str
    payload: dict[str, Any]
    error: str = ""


class Hungary26State:
    """Small explicit SQLite state store with downstream invalidation."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS records (
                    document_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    source_url TEXT,
                    post_id TEXT,
                    media_id TEXT NOT NULL,
                    workbook TEXT NOT NULL,
                    sheet TEXT NOT NULL,
                    row_number INTEGER NOT NULL,
                    source_fingerprint TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stages (
                    document_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (document_id, stage)
                );
                CREATE TABLE IF NOT EXISTS run_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def upsert_record(self, record: WorkbookRecord) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO records (
                    document_id, platform, source_url, post_id, media_id,
                    workbook, sheet, row_number, source_fingerprint, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    platform=excluded.platform,
                    source_url=excluded.source_url,
                    post_id=excluded.post_id,
                    media_id=excluded.media_id,
                    workbook=excluded.workbook,
                    sheet=excluded.sheet,
                    row_number=excluded.row_number,
                    source_fingerprint=excluded.source_fingerprint,
                    raw_json=excluded.raw_json
                """,
                (
                    record.document_id, record.platform, record.source_url, record.post_id,
                    record.media_id, record.workbook, record.sheet, record.row_number,
                    record.exact_fingerprint, stable_json(record.to_dict()),
                ),
            )

    def cached(self, document_id: str, stage: str, fingerprint: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM stages WHERE document_id=? AND stage=?",
                (document_id, stage),
            ).fetchone()
        if not row or row["status"] != "ok" or row["fingerprint"] != fingerprint:
            return None
        return json.loads(row["payload_json"])

    def write_stage(self, result: StageResult) -> None:
        with self.connect() as db:
            previous = db.execute(
                "SELECT attempt_count FROM stages WHERE document_id=? AND stage=?",
                (result.document_id, result.stage),
            ).fetchone()
            attempts = (int(previous["attempt_count"]) if previous else 0) + 1
            db.execute(
                """
                INSERT INTO stages (
                    document_id, stage, fingerprint, status, attempt_count,
                    payload_json, error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, stage) DO UPDATE SET
                    fingerprint=excluded.fingerprint,
                    status=excluded.status,
                    attempt_count=excluded.attempt_count,
                    payload_json=excluded.payload_json,
                    error=excluded.error,
                    updated_at=excluded.updated_at
                """,
                (
                    result.document_id, result.stage, result.fingerprint, result.status,
                    attempts, stable_json(result.payload), result.error, time.time(),
                ),
            )
            if result.status == "ok":
                index = STAGES.index(result.stage)
                for downstream in STAGES[index + 1:]:
                    db.execute(
                        "DELETE FROM stages WHERE document_id=? AND stage=? AND fingerprint<>?",
                        (result.document_id, downstream, result.fingerprint),
                    )

    def write_metadata(self, key: str, value: Any) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO run_metadata(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, stable_json(value)),
            )

    def rows(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            records = db.execute("SELECT * FROM records ORDER BY platform, document_id").fetchall()
            stages = db.execute("SELECT * FROM stages").fetchall()
        stage_map: dict[tuple[str, str], sqlite3.Row] = {
            (row["document_id"], row["stage"]): row for row in stages
        }
        output: list[dict[str, Any]] = []
        for row in records:
            raw = json.loads(row["raw_json"])
            flat = {
                **raw,
                "source_fingerprint": row["source_fingerprint"],
            }
            for stage in STAGES:
                item = stage_map.get((row["document_id"], stage))
                flat[f"{stage}_status"] = item["status"] if item else ""
                flat[f"{stage}_error"] = item["error"] if item else ""
                flat[f"{stage}_output"] = item["payload_json"] if item else ""
            output.append(flat)
        return output


def private_paths(root: str | Path) -> dict[str, Path]:
    base = Path(root)
    return {
        "root": base,
        "instagram": base / "source" / "hungary2026_instagram.xlsx",
        "tiktok": base / "source" / "hungary2026_tiktok.xlsx",
        "codebook": base / "codebooks" / "hungary26_private.json",
        "config": base / "run" / "hungary26_roihu.yaml",
        "db": base / "data" / "hungary26.sqlite3",
        "data": base / "data",
        "media": base / "media",
        "keyframes": base / "keyframes",
        "logs": base / "logs",
        "outputs": base / "outputs",
    }


def ensure_private_layout(root: str | Path) -> dict[str, Path]:
    paths = private_paths(root)
    required = ("instagram", "tiktok", "codebook", "config")
    missing = [str(paths[name]) for name in required if not paths[name].exists()]
    if missing:
        raise FileNotFoundError("Hungary26 private runtime missing:\n  - " + "\n  - ".join(missing))
    for name in ("data", "media", "keyframes", "logs", "outputs"):
        paths[name].mkdir(parents=True, exist_ok=True)
    return paths


def load_records(paths: dict[str, Path]) -> list[WorkbookRecord]:
    return [
        *load_hungary26_workbook(paths["instagram"], platform="instagram"),
        *load_hungary26_workbook(paths["tiktok"], platform="tiktok"),
    ]


def _config(path: Path) -> dict[str, Any]:
    import yaml
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def build_store(config: dict[str, Any]) -> S3ArtifactStore:
    bucket = str(config.get("allas_bucket") or os.getenv("LACLAUGPT_S3_BUCKET") or "")
    if not bucket:
        raise ValueError("Hungary26 Allas bucket is required in private config or LACLAUGPT_S3_BUCKET")
    return S3ArtifactStore(
        bucket=bucket,
        endpoint_url=str(config.get("allas_endpoint") or os.getenv("LACLAUGPT_S3_ENDPOINT_URL") or "") or None,
        region=str(config.get("allas_region") or os.getenv("LACLAUGPT_S3_REGION") or "") or None,
        prefix=str(config.get("allas_prefix") or ""),
        signature_version=str(config.get("allas_signature_version") or "s3"),
        addressing_style=str(config.get("allas_addressing_style") or "auto"),
    )


def normalize_object_ref(media_ref: str, bucket: str) -> str:
    ref = str(media_ref or "").strip()
    if not ref:
        return ""
    if ref.startswith("s3://"):
        return ref
    return f"s3://{bucket}/{ref.lstrip('/')}"


def extract_keyframes(video: Path, target_dir: Path, *, max_frames: int = 3) -> list[dict[str, Any]]:
    """Extract deterministic evenly-spaced frames without importing OpenCV."""
    target_dir.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        check=True, capture_output=True, text=True,
    )
    duration = max(float(probe.stdout.strip() or "0"), 0.0)
    if duration <= 0:
        timestamps = [0.0]
    else:
        count = min(max_frames, 3)
        timestamps = [duration * (i + 1) / (count + 1) for i in range(count)]
    frames: list[dict[str, Any]] = []
    for i, timestamp in enumerate(timestamps, start=1):
        target = target_dir / f"frame_{i:02d}.jpg"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{timestamp:.3f}", "-i", str(video), "-frames:v", "1",
             "-q:v", "2", str(target)],
            check=True,
        )
        frames.append({
            "frame_id": f"f{i}",
            "timestamp_seconds": round(timestamp, 3),
            "path": str(target),
            "sha256": sha256_file(target),
        })
    return frames


def ollama_chat(*, model: str, system: str, user: str,
                images: Iterable[str] = (), num_ctx: int = 32768,
                num_predict: int = 2048) -> str:
    if model != DEFAULT_MODEL and not os.getenv("LACLAUGPT_HUNGARY26_ALLOW_MODEL_OVERRIDE"):
        raise ValueError(f"Hungary26 Roihu test requires {DEFAULT_MODEL}; got {model}")
    import ollama
    message: dict[str, Any] = {"role": "user", "content": user}
    image_list = [str(Path(path)) for path in images]
    if image_list:
        for path in image_list:
            if not Path(path).is_file():
                raise FileNotFoundError(f"multimodal attachment is not a local file: {path}")
        message["images"] = image_list
    response = ollama.chat(
        model=model,
        messages=[{"role": "system", "content": system}, message],
        options={"temperature": 0.0, "num_ctx": num_ctx, "num_predict": num_predict},
    )
    return str(response["message"]["content"])


VISION_SYSTEM = """You are performing evidence-first multimodal social-science analysis.
Describe only what is directly visible in the supplied Hungary26 frame. Preserve Hungarian
text exactly when readable. Distinguish direct observation from interpretation. Do not infer
party alignment, ideology or populism from identity metadata. State uncertainty explicitly."""

SUMMARY_SYSTEM = """Synthesize Hungary26 source evidence conservatively. Separate caption,
visual observations, text-on-screen and any transcript. Preserve Hungarian wording as evidence.
Return JSON with keys summary, actors, entities, topics, evidence, uncertainty_notes."""

DISCOURSE_SYSTEM = """Perform cautious Laclau/Mouffe/Palonen-inspired discourse analysis of
the supplied Hungary26 evidence. Return JSON with keys signifiers, demands, collective_subjects,
frontiers, affects, chains_equivalence, chains_difference, nodal_point_candidates,
floating_signifier_candidates, empty_signifier_candidates, evidence, uncertainty_notes.
Co-occurrence is not articulation; disagreement is not automatically antagonism; actor or party
identity is context rather than proof. Abstain when evidence is weak."""


def _parse_object(raw: str) -> dict[str, Any]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("model JSON response must be an object")
    return parsed


def process_record(record: WorkbookRecord, *, state: Hungary26State, paths: dict[str, Path],
                   config: dict[str, Any], model: str, codebook_hash: str,
                   config_hash: str) -> None:
    state.upsert_record(record)
    fp = runtime_fingerprint(
        record=record, model=model, prompt_version="hungary26-roihu-v1",
        codebook_hash=codebook_hash, config_hash=config_hash,
    )
    bucket = str(config.get("allas_bucket") or os.getenv("LACLAUGPT_S3_BUCKET") or "")
    object_ref = normalize_object_ref(record.media_ref, bucket)
    if not object_ref:
        state.write_stage(StageResult(record.document_id, "download", fp, "error", {}, "missing media_ref"))
        return

    download = state.cached(record.document_id, "download", fp)
    if not download:
        try:
            store = build_store(config)
            stager = MediaStager(
                store,
                paths["media"],
                policy=StagingPolicy(max_cache_bytes=None, max_object_bytes=None, max_age_seconds=0),
                project_id="hungary26",
            )
            staged = stager.stage(object_ref)
            if not staged.local_available or staged.path is None:
                raise RuntimeError(staged.reason or staged.status)
            download = {
                "object_ref_hash": sha256_text(object_ref),
                "local_path": str(staged.path),
                "byte_size": staged.byte_size,
                "sha256": sha256_file(staged.path),
            }
            state.write_stage(StageResult(record.document_id, "download", fp, "ok", download))
        except Exception as exc:
            state.write_stage(StageResult(record.document_id, "download", fp, "error", {}, str(exc)))
            return

    frames_payload = state.cached(record.document_id, "frames", fp)
    if not frames_payload:
        try:
            frames = extract_keyframes(
                Path(download["local_path"]),
                paths["keyframes"] / record.document_id,
                max_frames=int(config.get("max_keyframes", 3)),
            )
            frames_payload = {"frames": frames}
            state.write_stage(StageResult(record.document_id, "frames", fp, "ok", frames_payload))
        except Exception as exc:
            state.write_stage(StageResult(record.document_id, "frames", fp, "error", {}, str(exc)))
            return

    vision = state.cached(record.document_id, "vision", fp)
    if not vision:
        try:
            observations = []
            for frame in frames_payload["frames"]:
                text = ollama_chat(
                    model=model,
                    system=VISION_SYSTEM,
                    user=f"Frame {frame['frame_id']} at {frame['timestamp_seconds']} seconds.",
                    images=[frame["path"]],
                    num_predict=int(config.get("vision_num_predict", 768)),
                )
                observations.append({**frame, "analysis": text, "evidence_type": "direct_image_pixels"})
            vision = {"observations": observations}
            state.write_stage(StageResult(record.document_id, "vision", fp, "ok", vision))
        except Exception as exc:
            state.write_stage(StageResult(record.document_id, "vision", fp, "error", {}, str(exc)))
            return

    summary = state.cached(record.document_id, "summary", fp)
    if not summary:
        try:
            prompt = stable_json({
                "caption_hu": record.caption,
                "visual_observations": vision["observations"],
                "source_provenance": {
                    "workbook": record.workbook, "sheet": record.sheet, "row": record.row_number,
                },
            })
            raw = ollama_chat(model=model, system=SUMMARY_SYSTEM, user=prompt)
            summary = {"raw": raw, "parsed": _parse_object(raw)}
            state.write_stage(StageResult(record.document_id, "summary", fp, "ok", summary))
        except Exception as exc:
            state.write_stage(StageResult(record.document_id, "summary", fp, "error", {}, str(exc)))
            return

    if not state.cached(record.document_id, "discourse", fp):
        try:
            prompt = stable_json({
                "caption_hu": record.caption,
                "multimodal_summary": summary["parsed"],
                "visual_evidence": vision["observations"],
            })
            raw = ollama_chat(model=model, system=DISCOURSE_SYSTEM, user=prompt)
            discourse = {"raw": raw, "parsed": _parse_object(raw)}
            state.write_stage(StageResult(record.document_id, "discourse", fp, "ok", discourse))
        except Exception as exc:
            state.write_stage(StageResult(record.document_id, "discourse", fp, "error", {}, str(exc)))


def export_csvs(state: Hungary26State, paths: dict[str, Path]) -> dict[str, str]:
    import pandas as pd
    rows = state.rows()
    frame = pd.DataFrame(rows)
    targets: dict[str, str] = {}
    for platform in ("instagram", "tiktok"):
        target = paths["data"] / f"{platform}.csv"
        frame[frame["platform"] == platform].to_csv(target, index=False)
        targets[platform] = str(target)
    combined = paths["data"] / "combined.csv"
    frame.to_csv(combined, index=False)
    targets["combined"] = str(combined)
    failure_cols = [col for col in frame.columns if col.endswith("_status") or col.endswith("_error")]
    failures = frame[frame[[c for c in failure_cols if c.endswith("_status")]].eq("error").any(axis=1)]
    failure_target = paths["data"] / "failures.csv"
    failures.to_csv(failure_target, index=False)
    targets["failures"] = str(failure_target)
    return targets


def select_records(records: list[WorkbookRecord], mode: str) -> list[WorkbookRecord]:
    if mode == "smoke":
        selected = []
        for platform in ("instagram", "tiktok"):
            candidates = sorted((r for r in records if r.platform == platform), key=lambda r: r.document_id)
            if candidates:
                selected.append(candidates[0])
        return selected
    if mode == "pilot":
        return deterministic_pilot(records, per_platform=6)
    return records


def preflight(root: Path, model: str) -> dict[str, Any]:
    paths = ensure_private_layout(root)
    if model != DEFAULT_MODEL:
        raise ValueError(f"model must be {DEFAULT_MODEL}")
    for binary in ("ffmpeg", "ffprobe"):
        subprocess.run([binary, "-version"], check=True, capture_output=True)
    codebook_hash = sha256_file(paths["codebook"])
    config_hash = sha256_file(paths["config"])
    state = Hungary26State(paths["db"])
    state.write_metadata("preflight", {"model": model, "codebook_hash": codebook_hash, "config_hash": config_hash})
    return {
        "ok": True,
        "private_root": str(root),
        "model": model,
        "sqlite": str(paths["db"]),
        "codebook_hash": codebook_hash,
        "config_hash": config_hash,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="laclaugpt-hungary26-roihu")
    parser.add_argument("mode", choices=("preflight", "smoke", "pilot", "full", "resume"), nargs="?", default="smoke")
    parser.add_argument("--private-root", type=Path, default=Path(os.getenv("LACLAUGPT_HUNGARY26_PRIVATE_ROOT", str(DEFAULT_PRIVATE_ROOT))))
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", DEFAULT_MODEL))
    args = parser.parse_args(argv)

    report = preflight(args.private_root, args.model)
    if args.mode == "preflight":
        print(json.dumps(report, indent=2))
        return 0

    paths = ensure_private_layout(args.private_root)
    config = _config(paths["config"])
    config["model"] = DEFAULT_MODEL
    state = Hungary26State(paths["db"])
    records = select_records(load_records(paths), args.mode)
    codebook_hash = sha256_file(paths["codebook"])
    config_hash = sha256_text(stable_json(config))

    state.write_metadata("run", {
        "mode": args.mode,
        "model": DEFAULT_MODEL,
        "record_count": len(records),
        "codebook_hash": codebook_hash,
        "config_hash": config_hash,
    })
    for record in records:
        process_record(
            record, state=state, paths=paths, config=config, model=DEFAULT_MODEL,
            codebook_hash=codebook_hash, config_hash=config_hash,
        )

    csvs = export_csvs(state, paths)
    result = {**report, "mode": args.mode, "records_selected": len(records), "csvs": csvs}
    target = paths["outputs"] / f"roihu-test-{os.getenv('SLURM_JOB_ID', 'local')}.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
