"""EP24 Finland/Poland Phase 1 multimodal reprocessing for CSC Roihu.

This study-specific runner stays isolated from the Phase 0 core. It uses local
files + SQLite + CSV, materializes media before inference, preserves original
and derived representations separately, runs the descriptive Phase 1
social-semiotic pass before discourse analysis, and never uses MongoDB, Redis,
or cloud fallback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hungary26_roihu import (
    build_store,
    extract_keyframes,
    normalize_object_ref,
    ollama_chat,
    sha256_file,
)
from .social_semiotic import (
    MultimodalSummaryProposal,
    assert_preanalysis_boundary,
)
from .staging import MediaStager, StagingPolicy

DEFAULT_MODEL = "gemma4:12b"
DEFAULT_PRIVATE_ROOT = Path("/scratch/project_2009497/LaclauGPT-Private/analysis/ep24")
PROMPT_VERSION = "ep24-phase1-multimodal-v2"
PREANALYSIS_PROMPT_VERSION = "social-semiotic-preanalysis.v2"
STAGES = ("normalize", "media", "representations", "preanalysis", "analysis", "postprocess")
TEXT_FIELDS = (
    "caption", "text", "description", "source_recording",
    "whisper_transcript", "whisper_translated", "summary_analysis",
)
OCR_FIELDS = ("ocr_1", "ocr_2", "ocr_3", "ocr_4", "ocr_5", "ocr_6")
MEDIA_FIELDS = (
    "local_media_path", "media_path", "video_path", "image_path",
    "allas_object", "allas_ref", "s3_uri", "media_ref",
)
URL_FIELDS = ("source_url", "url", "post_url", "video_url")
POLITICAL_PREANALYSIS_KEYS = {
    "empty_signifiers", "floating_signifiers", "nodal_points", "frontiers",
    "ideology", "populism", "political_alignment", "hegemony",
    "political_demands", "sentiment",
}


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"nan", "none", "null"} else text


def source_text(row: dict[str, Any]) -> str:
    chunks: list[str] = []
    seen: set[str] = set()
    for field in TEXT_FIELDS:
        value = clean(row.get(field))
        if value and value not in seen:
            chunks.append(f"[{field}] {value}")
            seen.add(value)
    return "\n".join(chunks)


def stable_record_id(row: dict[str, Any], *, country: str, source_name: str, row_number: int) -> str:
    for field in ("new_id", "video_id", "old_id", "source_url", "source_recording"):
        value = clean(row.get(field))
        if value:
            token = sha256_text(country + "|" + field + "|" + value)[:20]
            return f"ep24-{country.lower()}-{token}"
    payload = stable_json({"country": country, "source": source_name, "row": row_number, "data": row})
    return f"ep24-{country.lower()}-{sha256_text(payload)[:20]}"


def private_paths(root: str | Path) -> dict[str, Path]:
    base = Path(root)
    return {
        "root": base,
        "research_notes": base / "source" / "research_notes.xlsx",
        "entities": base / "source" / "entities.xlsx",
        "themes": base / "source" / "themes.xlsx",
        "finland": base / "source" / "ep24_finland_dashboard_9_1_2026.csv",
        "poland": base / "source" / "ep24_poland_dashboard_9_1_2026.csv",
        "common_codebook": base / "codebooks" / "ep24_common_private.json",
        "fi_codebook": base / "codebooks" / "ep24_finland_private.json",
        "pl_codebook": base / "codebooks" / "ep24_poland_private.json",
        "config": base / "run" / "ep24_roihu.yaml",
        "db": base / "data" / "ep24.sqlite3",
        "data": base / "data",
        "media": base / "media",
        "keyframes": base / "keyframes",
        "logs": base / "logs",
        "outputs": base / "outputs",
        "qa": base / "qa",
        "provenance": base / "provenance",
    }


def ensure_private_layout(root: str | Path) -> dict[str, Path]:
    paths = private_paths(root)
    required = (
        "research_notes", "entities", "themes", "finland", "poland",
        "common_codebook", "fi_codebook", "pl_codebook", "config",
    )
    missing = [str(paths[key]) for key in required if not paths[key].exists()]
    if missing:
        raise FileNotFoundError("EP24 private runtime missing:\n  - " + "\n  - ".join(missing))
    for key in ("data", "media", "keyframes", "logs", "outputs", "qa", "provenance"):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def _book_item(item: dict[str, Any], kind: str, country: str) -> dict[str, Any] | None:
    label = clean(item.get("label") or item.get("name") or item.get("canonical"))
    if not label:
        return None
    aliases = item.get("aliases") or item.get("surface_forms") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    return {
        "id": clean(item.get("id")) or sha256_text(f"{country}|{kind}|{label.casefold()}")[:16],
        "kind": clean(item.get("kind")) or kind,
        "label": label,
        "aliases": [clean(value) for value in aliases if clean(value)],
        "country": clean(item.get("country")) or country,
        "status": clean(item.get("status")) or "researcher-grounded",
        "provenance": item.get("provenance") or item.get("source") or "private-researcher",
    }


def load_private_codebooks(paths: dict[str, Path]) -> tuple[list[dict[str, Any]], str]:
    entries: list[dict[str, Any]] = []
    hashes: list[str] = []
    for country, key in (("COMMON", "common_codebook"), ("FI", "fi_codebook"), ("PL", "pl_codebook")):
        path = paths[key]
        payload = json.loads(path.read_text(encoding="utf-8"))
        hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
        candidates: list[tuple[str, dict[str, Any]]] = []
        for item in payload.get("entries", []) or []:
            if isinstance(item, dict):
                candidates.append((clean(item.get("kind")) or "concept", item))
        for field, kind in (
            ("entities", "entity"), ("themes", "theme"),
            ("signifiers", "signifier"), ("actors", "entity"),
        ):
            for item in payload.get(field, []) or []:
                candidates.append((kind, {"label": item} if isinstance(item, str) else item))
        for kind, item in candidates:
            if isinstance(item, dict):
                normalized = _book_item(item, kind, country)
                if normalized:
                    entries.append(normalized)
    alias_index: dict[str, set[str]] = {}
    for entry in entries:
        for form in [entry["label"], *entry["aliases"]]:
            alias_index.setdefault(form.casefold(), set()).add(entry["id"])
    collisions = sorted(key for key, ids in alias_index.items() if len(ids) > 1)
    if collisions:
        raise ValueError("Ambiguous EP24 codebook aliases: " + ", ".join(collisions[:20]))
    return entries, sha256_text("|".join(hashes))


def match_codebook(text: str, entries: list[dict[str, Any]], *, country: str) -> list[dict[str, Any]]:
    haystack = text.casefold()
    output: list[dict[str, Any]] = []
    for entry in entries:
        if clean(entry.get("country")).upper() not in {"", "COMMON", country.upper()}:
            continue
        hit = next(
            (form for form in [entry["label"], *entry["aliases"]] if form.casefold() in haystack),
            None,
        )
        if hit:
            output.append({
                "id": entry["id"], "kind": entry["kind"], "label": entry["label"],
                "matched_surface": hit, "status": entry["status"], "provenance": entry["provenance"],
            })
    return output


@dataclass(frozen=True)
class StageResult:
    record_id: str
    stage: str
    fingerprint: str
    status: str
    payload: dict[str, Any]
    error: str = ""


class EP24State:
    """Explicit SQLite state plus normalized Phase 1 evidence tables."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init(self) -> None:
        evidence_tables = (
            "representations", "media_assets", "source_units", "alignments", "asr", "ocr",
            "frames", "social_semiotic_preanalysis", "relations", "legacy_annotations",
            "discourse_analysis", "postprocess", "comparative_analysis", "uncertainties",
        )
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS records(
                    record_id TEXT PRIMARY KEY,country TEXT,language TEXT,source_file TEXT,
                    row_number INTEGER,source_fingerprint TEXT,legacy_fingerprint TEXT,raw_json TEXT
                );
                CREATE TABLE IF NOT EXISTS stages(
                    record_id TEXT,stage TEXT,fingerprint TEXT,status TEXT,attempt_count INTEGER,
                    payload_json TEXT,error TEXT,updated_at REAL,PRIMARY KEY(record_id,stage)
                );
                CREATE TABLE IF NOT EXISTS failures(
                    record_id TEXT,stage TEXT,error TEXT,updated_at REAL
                );
                CREATE TABLE IF NOT EXISTS run_metadata(key TEXT PRIMARY KEY,value TEXT);
                """
            )
            for table in evidence_tables:
                db.execute(
                    f"""CREATE TABLE IF NOT EXISTS {table}(
                        record_id TEXT NOT NULL,item_id TEXT NOT NULL,payload_json TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,created_at REAL NOT NULL,
                        PRIMARY KEY(record_id,item_id)
                    )"""
                )

    def upsert(
        self, record_id: str, country: str, language: str, source_file: str, row_number: int,
        source_fp: str, legacy_fp: str, row: dict[str, Any],
    ) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO records VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(record_id) DO UPDATE SET
                country=excluded.country,language=excluded.language,source_file=excluded.source_file,
                row_number=excluded.row_number,source_fingerprint=excluded.source_fingerprint,
                legacy_fingerprint=excluded.legacy_fingerprint,raw_json=excluded.raw_json""",
                (record_id, country, language, source_file, row_number, source_fp, legacy_fp, stable_json(row)),
            )

    def cached(self, record_id: str, stage: str, fingerprint: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM stages WHERE record_id=? AND stage=?", (record_id, stage)
            ).fetchone()
        return (
            json.loads(row["payload_json"])
            if row and row["status"] == "ok" and row["fingerprint"] == fingerprint else None
        )

    def write(self, result: StageResult) -> None:
        with self.connect() as db:
            previous = db.execute(
                "SELECT attempt_count FROM stages WHERE record_id=? AND stage=?",
                (result.record_id, result.stage),
            ).fetchone()
            attempts = (int(previous["attempt_count"]) if previous else 0) + 1
            db.execute(
                """INSERT INTO stages VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(record_id,stage) DO UPDATE SET
                fingerprint=excluded.fingerprint,status=excluded.status,
                attempt_count=excluded.attempt_count,payload_json=excluded.payload_json,
                error=excluded.error,updated_at=excluded.updated_at""",
                (
                    result.record_id, result.stage, result.fingerprint, result.status, attempts,
                    stable_json(result.payload), result.error, time.time(),
                ),
            )
            if result.status != "ok":
                db.execute(
                    "INSERT INTO failures VALUES(?,?,?,?)",
                    (result.record_id, result.stage, result.error, time.time()),
                )
            else:
                index = STAGES.index(result.stage)
                for downstream in STAGES[index + 1:]:
                    db.execute(
                        "DELETE FROM stages WHERE record_id=? AND stage=? AND fingerprint<>?",
                        (result.record_id, downstream, result.fingerprint),
                    )

    def evidence(self, table: str, record_id: str, item_id: str, payload: Any, fingerprint: str) -> None:
        allowed = {
            "representations", "media_assets", "source_units", "alignments", "asr", "ocr",
            "frames", "social_semiotic_preanalysis", "relations", "legacy_annotations",
            "discourse_analysis", "postprocess", "comparative_analysis", "uncertainties",
        }
        if table not in allowed:
            raise ValueError(f"unsupported evidence table: {table}")
        with self.connect() as db:
            db.execute(
                f"""INSERT INTO {table}(record_id,item_id,payload_json,fingerprint,created_at)
                VALUES(?,?,?,?,?) ON CONFLICT(record_id,item_id) DO UPDATE SET
                payload_json=excluded.payload_json,fingerprint=excluded.fingerprint,
                created_at=excluded.created_at""",
                (record_id, item_id, stable_json(payload), fingerprint, time.time()),
            )

    def metadata(self, key: str, value: Any) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO run_metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, stable_json(value)),
            )

    def rows(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            records = db.execute("SELECT * FROM records ORDER BY country,row_number").fetchall()
            stages = db.execute("SELECT * FROM stages").fetchall()
        stage_map = {(row["record_id"], row["stage"]): row for row in stages}
        output: list[dict[str, Any]] = []
        for rec in records:
            row = json.loads(rec["raw_json"])
            row.update({
                "ep24_record_id": rec["record_id"], "ep24_country": rec["country"],
                "ep24_language": rec["language"], "ep24_source_file": rec["source_file"],
                "ep24_source_row": rec["row_number"], "ep24_source_fingerprint": rec["source_fingerprint"],
                "ep24_legacy_fingerprint": rec["legacy_fingerprint"],
            })
            for stage in STAGES:
                item = stage_map.get((rec["record_id"], stage))
                row[f"ep24_{stage}_status"] = item["status"] if item else ""
                row[f"ep24_{stage}_error"] = item["error"] if item else ""
                row[f"ep24_{stage}_json"] = item["payload_json"] if item else ""
            output.append(row)
        return output


def _media_mapping(config: dict[str, Any]) -> dict[str, str]:
    mapping = config.get("media_mapping") or {}
    if isinstance(mapping, dict):
        return {str(key): str(value) for key, value in mapping.items()}
    return {}


def resolve_media_ref(row: dict[str, Any], config: dict[str, Any]) -> str:
    for field in MEDIA_FIELDS:
        value = clean(row.get(field))
        if value:
            return value
    mapping = _media_mapping(config)
    for field in ("new_id", "video_id", "old_id", *URL_FIELDS):
        value = clean(row.get(field))
        if value and value in mapping:
            return mapping[value]
    return ""


def _materialize_local(source: Path, target_dir: Path, record_id: str) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix or ".bin"
    target = target_dir / f"{record_id}{suffix}"
    if target.exists() and sha256_file(target) == sha256_file(source):
        return target
    shutil.copy2(source, target)
    return target


def materialize_media(
    *, row: dict[str, Any], record_id: str, paths: dict[str, Path],
    config: dict[str, Any],
) -> dict[str, Any]:
    ref = resolve_media_ref(row, config)
    if not ref:
        return {"coverage": "not_provided", "source_ref": "", "local_path": ""}
    candidate = Path(os.path.expanduser(ref))
    try:
        if candidate.is_file():
            local = _materialize_local(candidate, paths["media"], record_id)
        else:
            bucket = str(config.get("allas_bucket") or os.getenv("LACLAUGPT_S3_BUCKET") or "")
            if not bucket:
                return {"coverage": "not_processed", "source_ref": ref, "local_path": "", "reason": "no Allas bucket configured"}
            object_ref = normalize_object_ref(ref, bucket)
            stager = MediaStager(
                build_store(config), paths["media"],
                policy=StagingPolicy(max_cache_bytes=None, max_object_bytes=None, max_age_seconds=0),
                project_id="ep24",
            )
            staged = stager.stage(object_ref)
            if not staged.local_available or staged.path is None:
                raise RuntimeError(staged.reason or staged.status)
            local = Path(staged.path)
        mime = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
        size = local.stat().st_size
        if size <= 0:
            raise ValueError("materialized media is empty")
        return {
            "coverage": "processed", "source_ref": ref, "local_path": str(local),
            "byte_size": size, "sha256": sha256_file(local), "mime_type": mime,
        }
    except Exception as exc:
        return {
            "coverage": "failed", "source_ref": ref, "local_path": "",
            "reason": str(exc),
        }


def existing_representations(row: dict[str, Any], record_id: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    caption = source_text(row)
    if caption:
        items.append({
            "representation_id": f"{record_id}:source-text", "type": "source_text",
            "modality": "linguistic", "text": caption, "verification": "original_or_legacy_source",
        })
    for index, field in enumerate(OCR_FIELDS, start=1):
        value = clean(row.get(field))
        if value:
            items.append({
                "representation_id": f"{record_id}:legacy-ocr:{index}", "type": "ocr",
                "modality": "typographic", "text": value,
                "verification": "legacy-derived-not-reverified",
            })
    transcript = clean(row.get("whisper_transcript"))
    if transcript:
        items.append({
            "representation_id": f"{record_id}:legacy-asr", "type": "asr",
            "modality": "auditory", "text": transcript,
            "verification": "legacy-derived-not-reverified",
        })
    translated = clean(row.get("whisper_translated"))
    if translated:
        items.append({
            "representation_id": f"{record_id}:legacy-asr-translation", "type": "translation",
            "modality": "linguistic", "text": translated,
            "verification": "legacy-derived-not-reverified",
        })
    return {"items": items}


def _is_image(path: Path) -> bool:
    return path.suffix.casefold() in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def _is_video(path: Path) -> bool:
    return path.suffix.casefold() in {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def derive_frames(media: dict[str, Any], paths: dict[str, Path], record_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    if media.get("coverage") != "processed":
        return []
    path = Path(media["local_path"])
    if _is_image(path):
        return [{
            "frame_id": "f1", "timestamp_seconds": 0.0, "path": str(path),
            "sha256": media["sha256"], "source": "still_image",
        }]
    if _is_video(path):
        return extract_keyframes(
            path, paths["keyframes"] / record_id,
            max_frames=int(config.get("max_keyframes", 3)),
        )
    return []


def maybe_transcribe_audio(media: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Optional local ASR. Missing provider is an explicit coverage state, never silent."""
    if media.get("coverage") != "processed":
        return {"coverage": "not_provided", "text": ""}
    if not bool(config.get("enable_asr", False)):
        return {"coverage": "not_processed", "text": "", "reason": "enable_asr=false"}
    try:
        from faster_whisper import WhisperModel  # optional/lazy Roihu dependency
    except Exception as exc:
        return {"coverage": "unsupported", "text": "", "reason": f"faster-whisper unavailable: {exc}"}
    try:
        model_name = str(config.get("asr_model", "large-v3-turbo"))
        model = WhisperModel(model_name, device="cuda", compute_type=str(config.get("asr_compute_type", "float16")))
        segments, info = model.transcribe(str(media["local_path"]), beam_size=1, vad_filter=True)
        parts: list[str] = []
        spans: list[dict[str, Any]] = []
        for index, segment in enumerate(segments):
            text = clean(segment.text)
            if text:
                parts.append(text)
                spans.append({
                    "segment_id": index, "start": float(segment.start), "end": float(segment.end), "text": text,
                })
        return {
            "coverage": "processed", "text": " ".join(parts), "segments": spans,
            "language": getattr(info, "language", ""), "model": model_name,
        }
    except Exception as exc:
        return {"coverage": "failed", "text": "", "reason": str(exc)}


PREANALYSIS_SYSTEM = """Perform Phase 1 multimodal social-semiotic pre-analysis only.
Be descriptive, evidence-anchored, modality-preserving, and uncertainty-preserving.
Do not classify ideology, party alignment, populism, sentiment, hegemony, antagonistic
frontiers, political demands/subjects, nodal points, empty/floating signifiers, or
equivalence/difference chains. Return one JSON object matching the supplied schema shape.
Keep exact source-language text when directly evidenced. Every substantive observation
must cite evidence_ids tied to source text, OCR, ASR, or a frame/timestamp."""


DISCOURSE_SYSTEM = """Perform cautious evidence-first Laclau/Mouffe/Palonen analysis using
the validated Phase 1 descriptive pre-analysis plus researcher-grounded normalization
context. Return one JSON object with list-valued keys: entities, themes, signifiers,
demands, collective_subjects, frontiers, affects, chains_equivalence, chains_difference,
nodal_point_candidates, floating_signifier_candidates, empty_signifier_candidates,
evidence, uncertainty_notes. Researcher codebook matches are context, not proof.
Co-occurrence is not articulation; criticism is not automatically antagonism; abstain
when evidence is weak."""


ANALYSIS_KEYS = (
    "entities", "themes", "signifiers", "demands", "collective_subjects", "frontiers",
    "affects", "chains_equivalence", "chains_difference", "nodal_point_candidates",
    "floating_signifier_candidates", "empty_signifier_candidates", "evidence",
    "uncertainty_notes",
)


def parse_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = "```"
    if text.startswith(fence):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == fence:
            lines = lines[:-1]
        text = "\n".join(lines)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("model response must be JSON object")
    return payload


def run_preanalysis(
    *, model: str, record_id: str, country: str, language: str,
    representations: dict[str, Any], frames: list[dict[str, Any]], config: dict[str, Any],
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    for item in representations["items"]:
        modality = item["modality"]
        if modality not in {"linguistic", "visual", "auditory", "typographic", "metadata"}:
            modality = "other"
        evidence.append({
            "evidence_id": item["representation_id"], "modality": modality,
            "source_ref": item["type"], "exact_text": item.get("text", ""),
            "confidence": "medium" if item.get("verification", "").startswith("legacy") else "high",
            "uncertainty": item.get("verification", ""),
        })
    frame_refs = []
    for frame in frames:
        eid = f"{record_id}:frame:{frame['frame_id']}"
        evidence.append({
            "evidence_id": eid, "modality": "visual", "source_ref": frame["path"],
            "frame_id": frame["frame_id"], "timestamp_start": frame.get("timestamp_seconds", 0.0),
            "confidence": "high",
        })
        frame_refs.append({**frame, "evidence_id": eid})
    missing = []
    present = sorted({item["modality"] for item in evidence})
    if "visual" not in present:
        missing.append("visual")
    if "auditory" not in present:
        missing.append("auditory")
    skeleton = {
        "schema_version": "social-semiotic-preanalysis.v1",
        "prompt_version": PREANALYSIS_PROMPT_VERSION,
        "source_languages": [language] if language else [],
        "modalities_present": present,
        "modalities_missing": missing,
        "evidence": evidence,
    }
    prompt = stable_json({
        "record_id": record_id, "country": country,
        "required_schema_seed": skeleton,
        "representations": representations["items"],
        "frames": [{k: v for k, v in frame.items() if k != "path"} for frame in frame_refs],
    })
    images = [frame["path"] for frame in frame_refs]
    raw = ollama_chat(
        model=model, system=PREANALYSIS_SYSTEM, user=prompt, images=images,
        num_ctx=int(config.get("num_ctx", 32768)),
        num_predict=int(config.get("preanalysis_num_predict", 3072)),
    )
    parsed = parse_object(raw)
    # Ensure the immutable evidence bundle survives even if the model omits it.
    parsed.setdefault("schema_version", "social-semiotic-preanalysis.v1")
    parsed.setdefault("prompt_version", PREANALYSIS_PROMPT_VERSION)
    parsed.setdefault("source_languages", skeleton["source_languages"])
    parsed.setdefault("modalities_present", skeleton["modalities_present"])
    parsed.setdefault("modalities_missing", skeleton["modalities_missing"])
    parsed.setdefault("evidence", skeleton["evidence"])
    assert_preanalysis_boundary(parsed)
    proposal = MultimodalSummaryProposal.model_validate(parsed)
    return {"raw": raw, "parsed": proposal.model_dump(mode="json")}


def run_discourse(
    *, model: str, country: str, preanalysis: dict[str, Any],
    matches: list[dict[str, Any]], config: dict[str, Any],
) -> dict[str, Any]:
    if os.getenv("LLM_ALLOW_CLOUD_FALLBACK", "0") not in {"0", "false", "False", ""}:
        raise ValueError("cloud fallback forbidden")
    host = os.getenv("OLLAMA_HOST", "")
    if host and "127.0.0.1" not in host and "localhost" not in host:
        raise ValueError("localhost Ollama required")
    raw = ollama_chat(
        model=model, system=DISCOURSE_SYSTEM,
        user=stable_json({
            "country": country,
            "phase1_social_semiotic_preanalysis": preanalysis["parsed"],
            "researcher_grounded_codebook_matches": matches,
        }),
        num_ctx=int(config.get("num_ctx", 32768)),
        num_predict=int(config.get("num_predict", 3072)),
    )
    payload = parse_object(raw)
    for key in ANALYSIS_KEYS:
        value = payload.get(key, [])
        payload[key] = value if isinstance(value, list) else ([] if value is None else [value])
    return {"raw": raw, "parsed": payload}


def load_rows(path: Path) -> list[dict[str, Any]]:
    import pandas as pd
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    rows = []
    for index, raw in frame.iterrows():
        row = {str(key): clean(value) for key, value in raw.to_dict().items()}
        row["ep24_input_row"] = int(index) + 2
        rows.append(row)
    return rows


def select_rows(fi: list[dict[str, Any]], pl: list[dict[str, Any]], mode: str, n: int):
    if mode == "smoke":
        n = 2
    if mode in {"smoke", "pilot"}:
        return [*[("FI", row) for row in fi[:n]], *[("PL", row) for row in pl[:n]]]
    return [*[("FI", row) for row in fi], *[("PL", row) for row in pl]]


def process(
    country: str, row: dict[str, Any], source_file: Path, state: EP24State,
    entries: list[dict[str, Any]], model: str, book_hash: str, config_hash: str,
    config: dict[str, Any], paths: dict[str, Path],
) -> None:
    rownum = int(row["ep24_input_row"])
    rid = stable_record_id(row, country=country, source_name=source_file.name, row_number=rownum)
    text = source_text(row)
    source_fp = sha256_text(stable_json(row))
    legacy = {
        "entities": [clean(row.get(key)) for key in ("entities", "spacy_entities", "new_entity") if clean(row.get(key))],
        "themes": [clean(row.get(key)) for key in ("topics", "political_themes", "new_theme") if clean(row.get(key))],
    }
    legacy_fp = sha256_text(stable_json(legacy))
    language = clean(row.get("whisper_language")) or ("fi" if country == "FI" else "pl")
    state.upsert(rid, country, language, source_file.name, rownum, source_fp, legacy_fp, row)
    fp = sha256_text(stable_json({
        "source": source_fp, "model": model, "prompt": PROMPT_VERSION,
        "codebook": book_hash, "config": config_hash,
    }))

    normalized = {"text": text, "language": language, "country": country}
    if state.cached(rid, "normalize", fp) is None:
        state.write(StageResult(rid, "normalize", fp, "ok", normalized))
        state.evidence("source_units", rid, "row", {
            "source_file": source_file.name, "row_number": rownum,
            "source_fingerprint": source_fp, "country": country, "language": language,
        }, fp)
        state.evidence("legacy_annotations", rid, "legacy", legacy, fp)

    media = state.cached(rid, "media", fp)
    if media is None:
        media = materialize_media(row=row, record_id=rid, paths=paths, config=config)
        status = "error" if media["coverage"] == "failed" else "ok"
        state.write(StageResult(rid, "media", fp, status, media, media.get("reason", "") if status == "error" else ""))
        state.evidence("media_assets", rid, "primary", media, fp)
        # Media failure does not abort a row if text/legacy derived evidence exists.
        if status == "error" and not text and not any(clean(row.get(field)) for field in OCR_FIELDS):
            return

    reps = state.cached(rid, "representations", fp)
    if reps is None:
        reps = existing_representations(row, rid)
        asr = maybe_transcribe_audio(media, config)
        if asr.get("text"):
            reps["items"].append({
                "representation_id": f"{rid}:asr", "type": "asr", "modality": "auditory",
                "text": asr["text"], "verification": "newly-generated", "segments": asr.get("segments", []),
            })
        frames = derive_frames(media, paths, rid, config)
        reps["frames"] = frames
        reps["asr_coverage"] = asr
        coverage = "processed" if reps["items"] or frames else "not_provided"
        reps["coverage"] = coverage
        state.write(StageResult(rid, "representations", fp, "ok", reps))
        for item in reps["items"]:
            state.evidence("representations", rid, item["representation_id"], item, fp)
            if item["type"] == "asr":
                state.evidence("asr", rid, item["representation_id"], item, fp)
            if item["type"] == "ocr":
                state.evidence("ocr", rid, item["representation_id"], item, fp)
        for frame in frames:
            state.evidence("frames", rid, frame["frame_id"], frame, fp)
        if asr.get("coverage") not in {"processed", "not_provided"}:
            state.evidence("uncertainties", rid, "asr-coverage", asr, fp)

    matches = match_codebook(
        "\n".join([item.get("text", "") for item in reps["items"]]), entries, country=country
    )

    preanalysis = state.cached(rid, "preanalysis", fp)
    if preanalysis is None:
        try:
            preanalysis = run_preanalysis(
                model=model, record_id=rid, country=country, language=language,
                representations=reps, frames=reps.get("frames", []), config=config,
            )
            state.write(StageResult(rid, "preanalysis", fp, "ok", preanalysis))
            state.evidence("social_semiotic_preanalysis", rid, PREANALYSIS_PROMPT_VERSION, preanalysis, fp)
            for index, relation in enumerate(preanalysis["parsed"].get("intermodal_relations", [])):
                state.evidence("relations", rid, f"intermodal-{index}", relation, fp)
            for index, uncertainty in enumerate(preanalysis["parsed"].get("uncertainty", [])):
                state.evidence("uncertainties", rid, f"preanalysis-{index}", uncertainty, fp)
        except Exception as exc:
            state.write(StageResult(rid, "preanalysis", fp, "error", {}, str(exc)))
            return

    analysis = state.cached(rid, "analysis", fp)
    if analysis is None:
        try:
            analysis = run_discourse(
                model=model, country=country, preanalysis=preanalysis,
                matches=matches, config=config,
            )
            state.write(StageResult(rid, "analysis", fp, "ok", analysis))
            state.evidence("discourse_analysis", rid, PROMPT_VERSION, analysis, fp)
        except Exception as exc:
            state.write(StageResult(rid, "analysis", fp, "error", {}, str(exc)))
            return

    if state.cached(rid, "postprocess", fp) is None:
        post = {
            "legacy": legacy, "new_entities": analysis["parsed"].get("entities", []),
            "new_themes": analysis["parsed"].get("themes", []),
            "codebook_matches": matches,
            "multimodal_coverage": {
                "media": media.get("coverage", "not_provided"),
                "asr": reps.get("asr_coverage", {}).get("coverage", "not_provided"),
                "frames": "processed" if reps.get("frames") else "not_provided",
            },
            "phase1_preanalysis_schema": preanalysis["parsed"].get("schema_version"),
        }
        state.write(StageResult(rid, "postprocess", fp, "ok", post))
        state.evidence("postprocess", rid, "canonical", post, fp)


def export(state: EP24State, paths: dict[str, Path]) -> dict[str, str]:
    import pandas as pd
    rows = state.rows()
    frame = pd.DataFrame(rows)
    outputs: dict[str, str] = {}
    for code, name in (("FI", "finland.csv"), ("PL", "poland.csv")):
        path = paths["data"] / name
        frame.loc[frame["ep24_country"] == code].to_csv(path, index=False)
        outputs[code] = str(path)
    combined = paths["data"] / "combined.csv"
    frame.to_csv(combined, index=False)
    outputs["combined"] = str(combined)
    with state.connect() as db:
        failures = [dict(row) for row in db.execute("SELECT * FROM failures")]
    failure_path = paths["data"] / "failures.csv"
    pd.DataFrame(failures).to_csv(failure_path, index=False)
    outputs["failures"] = str(failure_path)
    comparison = [{
        "ep24_record_id": row["ep24_record_id"], "country": row["ep24_country"],
        "legacy_json": row.get("ep24_postprocess_json", ""),
        "analysis_json": row.get("ep24_analysis_json", ""),
        "preanalysis_json": row.get("ep24_preanalysis_json", ""),
    } for row in rows]
    comparison_path = paths["data"] / "legacy_comparison.csv"
    pd.DataFrame(comparison).to_csv(comparison_path, index=False)
    outputs["legacy_comparison"] = str(comparison_path)
    return outputs


def preflight(root: str | Path, model: str):
    paths = ensure_private_layout(root)
    entries, book_hash = load_private_codebooks(paths)
    config = load_yaml(paths["config"])
    if config.get("cloud_fallback", False):
        raise ValueError("cloud_fallback must be false")
    for binary in ("ffmpeg", "ffprobe"):
        subprocess.run([binary, "-version"], check=True, capture_output=True)
    state = EP24State(paths["db"])
    with state.connect() as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return paths, entries, book_hash, config, {
        "private_root": str(paths["root"]), "model": model,
        "codebook_entries": len(entries), "codebook_hash": book_hash,
        "sqlite": str(paths["db"]), "cloud_fallback": False,
        "phase1_multimodal_tables": sorted(tables),
    }


def _git_sha(path: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def write_validation_report(
    *, paths: dict[str, Path], state: EP24State, mode: str, model: str,
    selected: list[tuple[str, dict[str, Any]]], outputs: dict[str, str],
) -> Path:
    rows = state.rows()
    counts = {
        stage: {
            "ok": sum(row.get(f"ep24_{stage}_status") == "ok" for row in rows),
            "error": sum(row.get(f"ep24_{stage}_status") == "error" for row in rows),
        }
        for stage in STAGES
    }
    job = os.getenv("SLURM_JOB_ID", "local")
    public_root = Path(__file__).resolve().parents[2]
    private_repo = paths["root"].parents[1]
    lines = [
        f"# EP24 Roihu reprocessing report {job}", "",
        f"- Mode: {mode}", f"- Model: {model}", f"- Slurm job ID: {job}",
        f"- Public Git SHA: {_git_sha(public_root)}",
        f"- Private Git SHA: {_git_sha(private_repo)}",
        f"- Records selected: {len(selected)}", f"- SQLite: {paths['db']}", "",
        "## Stage counts", "", "| Stage | OK | Error |", "| --- | ---: | ---: |",
        *[f"| {stage} | {counts[stage]['ok']} | {counts[stage]['error']} |" for stage in STAGES],
        "", "## Outputs", "", *[f"- {name}: {path}" for name, path in sorted(outputs.items())],
        "", "Phase 0 dependency isolation is covered by public regression tests.",
        "No sensitive source text is reproduced in this report.",
    ]
    target = paths["outputs"] / f"roihu-reprocess-{job}.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "smoke", "pilot", "full", "resume"), nargs="?", default="pilot")
    parser.add_argument("--private-root", default=os.getenv("LACLAUGPT_EP24_PRIVATE_ROOT", str(DEFAULT_PRIVATE_ROOT)))
    parser.add_argument("--model", default=os.getenv("EP24_ANALYSIS_MODEL", DEFAULT_MODEL))
    args = parser.parse_args(argv)

    paths, entries, book_hash, config, report = preflight(args.private_root, args.model)
    if args.mode == "preflight":
        print(json.dumps(report, indent=2))
        return 0

    state = EP24State(paths["db"])
    selected = select_rows(
        load_rows(paths["finland"]), load_rows(paths["poland"]),
        args.mode, int(config.get("pilot_size", 20)),
    )
    config_hash = sha256_text(stable_json(config))
    state.metadata("run", {
        "mode": args.mode, "model": args.model, "prompt": PROMPT_VERSION,
        "preanalysis_prompt": PREANALYSIS_PROMPT_VERSION, "codebook": book_hash,
        "config": config_hash, "record_count": len(selected),
    })
    for country, row in selected:
        process(
            country, row, paths["finland"] if country == "FI" else paths["poland"],
            state, entries, args.model, book_hash, config_hash, config, paths,
        )
    outputs = export(state, paths)
    validation = write_validation_report(
        paths=paths, state=state, mode=args.mode, model=args.model,
        selected=selected, outputs=outputs,
    )
    print(json.dumps({**report, "mode": args.mode, "outputs": outputs, "report": str(validation)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
