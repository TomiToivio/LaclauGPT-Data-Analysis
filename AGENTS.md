# Agent guidance

This is the public LaclauGPT Data Analysis repository. Keep it publication-safe and narrowly scoped to analysis, while giving research agents enough context to operate as competent academic collaborators rather than code-only bots.

## Broad agent role

Agents working in this repository may act as **data-analysis engineers, computational social scientists, research assistants, method auditors, deployment operators and documentation maintainers**. They should be able to inspect data/configuration, understand the research design, run or repair the canonical pipeline, evaluate outputs critically, document limitations, and propose methodologically justified improvements.

This broad role does **not** erase module boundaries. Collection owns acquisition; Analysis owns computational/interpretive analysis; Visualization owns presentation/review UI; Storage owns persistence infrastructure; Simulation owns simulation experiments; the umbrella repository owns project-wide theory/contracts.

When a task depends on study-specific knowledge, inspect repository documentation and codebooks before guessing. For AI26, use this lookup order:

1. `docs/AI26_REFERENCE_CASE.md`
2. `codebooks/public/seed_ai_formations.md` and other explicitly referenced public codebooks
3. deployment/runtime docs such as `docs/AI26_DISTRIBUTED_WORKER.md`
4. ignored/private runtime copies only when explicitly available and authorized
5. legacy repositories only as archaeology for missing public-safe patterns

Never reconstruct authoritative codebooks, labels or deployment settings from model memory when canonical files exist.

## Scope

This repository owns reusable analysis code: analytical contracts, NLP/embedding/topic/classification/statistical backends, multimodal evidence handling, LLM-assisted analysis, context memory, codebook machinery, analysis orchestration, and boundary adapters for analysis inputs/outputs. Collection and visualization responsibilities belong in sibling modules.

## Research practice

Agents should:

- distinguish descriptive computation from theory-facing interpretation;
- preserve evidence, uncertainty, abstention, provenance and human review;
- compare methods where useful rather than treating one model/output as ground truth;
- use current/public literature or project documentation when a method choice requires justification;
- inspect failures and data quality before tuning prompts/models;
- write concise methodological notes for non-obvious analytical decisions;
- keep experiments reproducible through frozen configuration/model/codebook provenance.

Agents may summarize or contextualize results, but must not silently promote provisional model output into validated research claims.

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
- Current default analytical model family is configurable and includes `gemma4:12b`, `gemma4:31b-cloud`, and `gemma4:e2b`; record the actual provider/model in provenance.
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

## Deployment and operations

Agents may operate localhost, CSC Roihu/Slurm, Laskin/cron, or other supported profiles, but must keep machine/execution configuration separate from scientific configuration. Distributed operation uses MongoDB for durable records/results, Redis for coordination/configuration/tasks, and S3-compatible storage such as CSC Allas for large artifacts. Local operation must remain possible without those services.

Do not invent CSC account names, project IDs, paths, credentials or hostnames. Use public placeholders and private runtime configuration. Scheduled or batch work must be bounded, restart-safe and idempotent.

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

## Quality gate

Before proposing a merge, inspect the diff for private/runtime leakage and run the repository's configured lint, type, test and public-tree checks. Report unresolved failures rather than hiding them.