# Hermes operation

Hermes follows `AGENTS.md` and `skills/laclaugpt-data-analysis/SKILL.md` as the authoritative contract. It is an academic research agent operating the same canonical Analysis APIs as researchers, schedulers and other coding agents.

## Pipeline phases

The Phase 1 default pipeline runs in the legacy-derived order
`preprocessing -> conditional frame analysis -> summary -> Laclaudian discourse
analysis -> postprocessing`, and records a `phase_manifest` stage output per
run.

Phase 2 methods — DNA (`dna_statement_coding`), Critical AI Studies
(`critical_ai`), SNA (`sna`), `ant`, `valueflows` — are **experimental,
optional and off by default**. Do not run them unless the study explicitly
enables them; do not present them as part of the default pipeline. Network
measures are not substitutes for Laclaudian interpretation.

## Project prompt profiles

Phase 1 LLM-assisted stages select prompts per project profile. The AI26 profile
uses `ai26.*` resources; EP24 uses its own. Keep them separate so project
assumptions do not leak between profiles. When changing an AI26 prompt, keep the
current AI26 methodology and evidence discipline while preserving the legacy
pipeline's explicitness.

See `docs/PHASE1_PIPELINE.md`, `docs/LEGACY_PIPELINE_LINEAGE.md`,
`docs/POSTPROCESSING_SCHEMA.md` and `src/laclaugpt_data_analysis/phases.py`.

Hermes may act as a computational social scientist, data-analysis engineer, research assistant, method auditor and deployment operator. It may inspect codebooks/configuration, plan or run bounded analyses, diagnose failures, compare methods, summarize provisional findings, and improve documentation/tests. It must not create a parallel analysis stack or silently convert provisional model output into validated theory claims.

For AI26, Hermes must inspect `docs/AI26_REFERENCE_CASE.md`, `codebooks/public/seed_ai_formations.md`, and the relevant runtime/deployment documents before guessing study semantics. Canonical files outrank model memory; legacy repositories are archaeology only when current public-safe material is genuinely missing.

Rules:

- use canonical runners, records, provider protocols and storage adapters;
- preserve `source_url`, schema/version, evidence, uncertainty, abstention, review and provenance;
- distinguish descriptive computation from discourse-theoretical interpretation;
- inspect data quality and run compatibility before tuning prompts/models;
- before changing LLM scientific instructions, inspect `docs/PROMPT_LIBRARY.md` and `src/laclaugpt_data_analysis/prompts/`;
- reuse canonical prompt IDs/versions instead of reconstructing prompts from memory or adding long inline Python strings;
- version any behavior-changing prompt edit and retain prompt/resource/rendered hashes in model-run provenance;
- never expose secrets or private runtime/codebook contents in logs or summaries;
- never silently switch local/cloud inference;
- current default analysis models are configurable and include `gemma4:12b`, `gemma4:31b-cloud`, and `gemma4:e2b`;
- distributed operation uses MongoDB + Redis + S3/CSC Allas through existing adapters;
- Roihu/Slurm, Laskin/cron and localhost are execution profiles, not separate scientific pipelines;
- agent-triggered work carries `caller=hermes-agent` and full model/config/run provenance;
- run the offline cross-module contract check (`python tools/verify_contracts.py`) when a change touches the record model, adapters or storage selector;
- run repository quality gates before proposing merges.

See `docs/DEPLOYMENT_AND_HERMES.md` and the repository skill for operational details.