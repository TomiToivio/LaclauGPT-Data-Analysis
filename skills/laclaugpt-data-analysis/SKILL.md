# LaclauGPT Data Analysis agent skill

Use this skill when an agent operates the Analysis module. The agent is not only a coding assistant: it may act as a computational social scientist, data-analysis engineer, research assistant, method auditor, deployment operator, and documentation maintainer, while remaining inside Analysis boundaries.

## First-read order

Before guessing study settings, codebooks, or analytical prompts, inspect canonical repository material. For AI26 use:

1. `docs/AI26_REFERENCE_CASE.md`
2. `codebooks/public/seed_ai_formations.md` and explicitly referenced codebooks
3. `docs/PROMPT_LIBRARY.md` and the canonical resources under `src/laclaugpt_data_analysis/prompts/` when an LLM-assisted method is involved
4. `docs/AI26_DISTRIBUTED_WORKER.md`, `docs/ANALYSIS_RUNTIME.md`, and deployment docs
5. the cross-module contracts (see "Cross-module contract conformance" below) when the record model, adapters or storage selector are involved
6. authorized ignored/private runtime copies when available
7. legacy repositories only as archaeology for genuinely missing public-safe patterns

Do not reconstruct authoritative settings, codebooks, or prompts from model memory when repository files exist.

## Scope

Analysis owns canonical enrichment of `CanonicalRecord`: NLP, embeddings, topic/statistical methods, multimodal evidence handling, LLM-assisted interpretation, context memory, codebooks, orchestration, validation, provenance, review semantics, and analysis exports. Collection, Visualization, Storage, Simulation, and umbrella project governance remain sibling responsibilities.

## Canonical prompt library

Treat prompts as part of the scientific method. Stable analytical instructions belong in the versioned prompt library under `src/laclaugpt_data_analysis/prompts/`, loaded through `PromptLibrary` / `load_prompt`, not as new inline Python strings or instructions reconstructed from memory.

When changing or adding LLM-assisted analysis:

- locate and reuse the canonical prompt resource before inventing a new one;
- keep system/method prompts, task templates, current source evidence, codebook/RAG context, and project/study context conceptually separate;
- use explicit semantic IDs and versions such as `laclau.system:v1`;
- create a new prompt version when wording, structure, or formatting can alter model behaviour instead of silently changing an existing version;
- preserve old referenced prompt versions needed for reproducibility;
- record prompt ID, prompt version, prompt SHA-256, source path, and rendered-prompt hash in model/run provenance where applicable;
- never put credentials, private corpora, private annotations, sensitive operational data, or private project inputs in public prompt resources;
- keep prompt-free statistical, network, deterministic NLP, and similar plugins prompt-free unless the method genuinely requires an LLM.

Evidence-first guardrails remain mandatory: codebooks, memory, and RAG are context rather than source evidence; abstention is valid; frequency is not hegemony; polysemy is not empty signification; negativity or sentiment is not antagonism; and document-level theoretical candidates may require corpus-level validation.

Before adding a scientific instruction string to Python, search `docs/PROMPT_LIBRARY.md` and the relevant method/plugin prompt directory. If no suitable resource exists, add a readable Markdown/text prompt with an explicit version and synthetic offline tests for loading, hashing, deterministic rendering, required-variable validation, and provenance.

## Research-assistant capabilities

Agents may:

- inspect and explain datasets, codebooks, pipeline stages, model runs and provenance;
- run bounded analyses and compare methods/models;
- investigate failed or surprising outputs;
- create reproducible notebooks/scripts/tests where appropriate;
- summarize provisional findings with explicit uncertainty;
- review relevant literature or current methodology when method choices need evidence;
- propose codebook/method changes without silently applying theoretical conclusions;
- prepare deployment/run instructions for localhost, Roihu/Slurm, Laskin/cron and other supported environments.

Computational outputs remain candidates/evidence. Topic clusters are not automatically discourses, embeddings are not equivalence relations, and model confidence is not theoretical confidence.

## AI26 semantics

AI26 is the realistic public reference case. Formation labels such as `accelerationism`, `doomerism`, `left-wing accelerationism`, `ai safety`, `ai critical`, and `anti-ai` are provisional sensitising/aggregation categories, not actor identities or keyword classifiers. Preserve overlap, uncertainty and abstention. Candidate signifiers and collection hints are context, not proof.

## Deployment dimensions

Compose independently:

- machine: `laptop`, `roihu`, `linux-server`, `custom`
- execution: `cli`, `slurm`, `cron`, `systemd`, `agent`, `custom`
- storage: `local`, `distributed`, `custom`
- LLM/provider: local Ollama, explicitly configured cloud Ollama/provider, or custom

Machine/execution settings must not fork scientific semantics. The same prompt IDs/versions and codebook/config revisions should travel across execution profiles unless a run explicitly selects a different version and records it in provenance.

## Storage and distributed operation

Local operation uses SQLite + CSV/JSONL/Pandas + filesystem under private `data/`. Distributed operation uses MongoDB for durable canonical records/results, Redis for configuration/coordination/task/lease state, and S3-compatible storage such as CSC Allas for large artifacts. `source_url` remains canonical identity everywhere.

Redis is infrastructure, not the scientific schema. Large blobs belong in object storage with references/checksums in canonical provenance.

## Models

Use the provider abstraction, not direct Ollama calls from scientific modules. Current default analysis model family includes `gemma4:12b`, `gemma4:31b-cloud`, and `gemma4:e2b`. Never silently fall back between local and cloud. Record actual model/provider plus exact prompt/config/codebook versions and hashes in provenance.

## Hermes / agent operations

Use `laclaugpt_data_analysis.integrations.hermes` and canonical runners to inspect redacted configuration, validate profiles, plan/dry-run, launch bounded analysis, inspect/resume runs, export canonical results, and stamp agent provenance. Agents must not bypass codebooks, validation, review, uncertainty, privacy, canonical prompt resources, or provenance controls.

## Scientific and data-quality checks

Before interpreting results, check data grain, missingness, duplicate identities, stale/incompatible run configuration, schema versions, source revisions, model failures, prompt/config/codebook revisions, and evidence availability. Prefer diagnosing data or pipeline defects before prompt-tuning around them.

## Privacy

Real corpora, private source lists, corpus-derived codebooks, researcher annotations, credentials, machine paths, CSC project identifiers and run state stay outside Git. Public Slurm/cron/systemd material uses placeholders. Tests use synthetic data and fake providers. Private prompt overlays, when genuinely required, belong in an authorized ignored/private runtime location while their version/hash still participates in provenance.

## Handoff

Same-host flow may read Collection's configured `data/` tree directly. Distributed flow uses canonical MongoDB records, Redis coordination and S3/Allas references. Visualization consumes canonical analysis results, not Analysis implementation internals.

## Cross-module contract conformance

Analysis is one stage of `Collection -> Analysis -> Visualization`. Three project-wide contracts are normative for this module and are owned by the meta-repository `TomiToivio/LaclauGPT`:

- `docs/CANONICAL_DATA_CONTRACT.md` — `source_url` is the semantic identity and MUST survive canonicalization and every storage/transport round trip unchanged. Backend IDs (`_id`, row numbers, object keys) never replace it.
- `docs/STORAGE_BACKEND_CONTRACT.md` — `auto | mongodb | csv` semantics, with local CSV/filesystem as a first-class zero-infrastructure mode and fail-closed behaviour for misconfiguration.
- `fixtures/cross_module/canonical_parity_v1.json` — the versioned schema-drift tripwire. A repository-local copy is vendored under `tests/fixtures/`; do not fork its semantics into a second incompatible fixture.

Run the offline conformance check before proposing a change that touches the record model, the adapters or the storage selector:

```bash
python tools/verify_contracts.py
```

It verifies the fixture invariants, that provisional review state is never promoted, that JSON/JSONL/CSV/SQLite reconstruct the same logical record, that the storage selector fails closed, and that the declared schema version is well formed. It contacts nothing and writes no research data; exit status is the gate. When a contract or fixture version changes, update the vendored copy and this tool together.

Do not treat a green local test suite as contract conformance: these checks are deliberately independent of the module's own unit tests, because a shared-schema break appears as a mismatch *between* modules rather than as a failing unit.

## Quality standard

Keep changes typed, reproducible, evidence-aware and reviewable. Add synthetic tests for behavior changes. For LLM-assisted changes, include prompt-library/provenance tests when semantics or rendering change. Run configured public-tree, lint, type and test gates before proposing a merge, and report unresolved failures explicitly.