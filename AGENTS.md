# Agent guidance

This is the public LaclauGPT Data Analysis repository. Keep it publication-safe and narrowly scoped.

## Scope

This repository owns reusable analysis code: analytical contracts, NLP/embedding/topic/classification/statistical backends, multimodal evidence handling, analysis orchestration, and boundary adapters for analysis inputs/outputs. Collection and visualization responsibilities belong in sibling modules.

## Canonical data contract

Read `docs/CANONICAL_RECORD.md` and the project-wide `TomiToivio/LaclauGPT/docs/CANONICAL_DATA_CONTRACT.md` before changing persisted models, exporters, storage adapters, multimodal contracts or analysis result schemas.

Mandatory rules:

- Analysis enriches `CanonicalRecord`; it does not invent a replacement persistent schema.
- `source_url` is the canonical source identity and must survive Collection -> Analysis -> Visualization unchanged.
- `document_id`, representation IDs, topic IDs, database PKs, Mongo `_id`, DataFrame row numbers and model-run IDs are aliases/derived IDs, never replacements for `source_url`.
- Descriptive NLP outputs and interpretive discourse claims remain distinguishable.
- Theory-facing/model-produced claims retain evidence/provenance and default to provisional/reviewable semantics.
- Text-only records remain valid; never manufacture empty multimodal observations to satisfy flat formats.
- CSV/Pandas, JSONL, SQLite, MongoDB and future Parquet adapters must reconstruct the same logical record.
- Nested values in flat formats use deterministic JSON encoding, never Python `repr`.
- Any persisted semantic schema change requires a version decision, migration note and synthetic contract/round-trip tests.
- Legacy EP24/monolith columns are adapter concerns only. Do not reintroduce numbered OCR/frame columns into canonical code.

## Mandatory runtime data boundary

All runtime and study-specific material belongs below `data/`, and the complete `data/` tree stays outside Git. Follow `docs/RUNTIME_DATA.md`.

Logs, local databases, runtime configuration, CSV/JSONL files, codebooks, source lists, downloaded files, media, transcripts, frames, exports, artifacts, temporary files and local Ollama/Whisper model material all belong under `data/`.

Do not create top-level `var/`, `logs/`, `database/`, `outputs/`, `downloads/` or model-cache roots. Use `Settings.data_dir`, `Settings.data_path()` and `Settings.ensure_local_directories()`.

When Collection and Analysis run on the same host, use the configured `collection_data_dir` to read canonical Collection data directly from the Collection module's `data/` tree. For distributed deployments use MongoDB, Redis and S3-compatible storage such as CSC Allas. CSV/JSONL is the manual fallback.

## Python architecture

- use `src/laclaugpt_data_analysis/`
- keep public contracts storage-neutral
- keep optional/heavy libraries lazy
- keep local CSV/SQLite/filesystem operation working without remote infrastructure
- add remote behavior through adapters
- avoid import-time network/model work
- use deterministic defaults and explicit provenance
- add tests for behavioral changes

## Methodological boundary

Computational outputs are evidence or candidates. Topic clusters are not automatically discourses; embedding similarity is not equivalence; model confidence is not theoretical confidence. Theory-facing classifications remain traceable to evidence, provenance and human review.

## Privacy and interoperability

Tests use synthetic data only. Public configuration contains examples/placeholders, while operational material belongs below `data/` or in external deployment systems.

Prefer the canonical versioned record at module boundaries. Avoid cross-repository imports of implementation internals; use serialized canonical records and bounded adapters instead.
