# Agent guidance

This is the public LaclauGPT Data Analysis repository. Keep it publication-safe and narrowly scoped.

## Scope

This repository owns reusable analysis code: analytical contracts, NLP/embedding/topic/classification/statistical backends, multimodal evidence handling, LLM-assisted analysis, context memory, codebook machinery, analysis orchestration, and boundary adapters for analysis inputs/outputs. Collection and visualization responsibilities belong in sibling modules.

## AI26 public reference study

AI26 (`Ideological contestation over AI`) is the preferred realistic public example for this module because the current LaclauGPT method and modular architecture are being developed alongside the public paper. Use `codebooks/public/seed_ai_formations.md` as the publication-safe conceptual reference, while keeping all analysis APIs study-agnostic.

The six AI26 computational formation labels (`accelerationism`, `doomerism`, `left-wing accelerationism`, `ai safety`, `ai critical`, `anti-ai`) are provisional sensitising categories and aggregation anchors, not a closed ontology. Do not infer them from actor identity, source list, keywords or a single statement. Multi-label overlap, uncertainty and abstention are valid.

Public codebooks may track paper- and situation-report-derived candidate signifiers/motifs such as safety, pacing, competition, innovation, China, control, liability, independent evaluation, regulation, labour, ownership, surveillance and data centres. Treat these as context/retrieval hints only. They are not evidence and must not silently become formations, nodal points, floating/empty signifiers, antagonisms or imaginaries.

The public/private rule for AI26 is **public methodology, private operations/data**. Public-safe conceptual codebooks, project/arena semantics and synthetic examples may be committed. Keep private row-level corpus data, private source/watch lists, unpublished annotations, credentials, private endpoints and machine-specific secrets.

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

## LLM/provider architecture

- All LLM-assisted analysis depends on the provider protocol under `llm/`; do not call Ollama directly from scientific/domain modules.
- Ollama is an optional adapter and must remain lazy-imported. No network call, model probe or model download occurs during package import.
- Cloud inference is explicit opt-in. Never silently fall back from local to cloud.
- Model/provider/endpoint/prompt-version details belong in analysis provenance/model-run metadata.
- Structured LLM output must be validated before it mutates canonical records.
- Fake providers are the default testing surface; live Ollama tests, if added, are opt-in only.

## Memory and codebooks

- Persistent stable-ID memory and runtime context retrieval are separate concerns.
- Local SQLite is the zero-infrastructure persistent-memory default.
- Codebook/memory retrieval supplies candidates/context, never source evidence.
- Resolution must support abstention and retain review/provenance semantics.
- Public conceptual codebooks and synthetic examples may be committed. Public-safe AI26 methodology is explicitly allowed. Private corpus-derived codebooks, entity/target lists and researcher annotations belong under ignored `data/codebooks/`, private repositories or external storage.
- Do not create duplicate `memory` packages or parallel type systems when the canonical memory models can be extended.

## Mandatory runtime data boundary

All runtime and operational study material belongs below `data/`, and the complete `data/` tree stays outside Git. Follow `docs/RUNTIME_DATA.md`.

Logs, local databases, runtime configuration, CSV/JSONL files, private codebooks, private source lists, downloaded files, media, transcripts, frames, exports, artifacts, temporary files and local Ollama/Whisper model material all belong under `data/`.

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
- avoid giant `pipeline.py`, `utils.py`, and `helpers.py` dumping grounds
- prefer protocols and small cohesive packages over backend-specific branching throughout scientific code

## Methodological boundary

Computational outputs are evidence or candidates. Topic clusters are not automatically discourses; embedding similarity is not equivalence; model confidence is not theoretical confidence. Theory-facing classifications remain traceable to evidence, provenance and human review.

## Privacy and interoperability

Tests use synthetic data only. Public configuration contains examples/placeholders and public-safe AI26 methodology, while operational material belongs below `data/` or in external deployment systems.

Prefer the canonical versioned record at module boundaries. Avoid cross-repository imports of implementation internals; use serialized canonical records and bounded adapters instead.
