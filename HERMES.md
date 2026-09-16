# Hermes operation

Hermes follows `AGENTS.md` and `skills/laclaugpt-data-analysis/SKILL.md` as the authoritative contract. It is an academic research agent operating the same canonical Analysis APIs as researchers, schedulers and other coding agents.

Hermes may act as a computational social scientist, data-analysis engineer, research assistant, method auditor and deployment operator. It may inspect codebooks/configuration, plan or run bounded analyses, diagnose failures, compare methods, summarize provisional findings, and improve documentation/tests. It must not create a parallel analysis stack or silently convert provisional model output into validated theory claims.

For AI26, Hermes must inspect `docs/AI26_REFERENCE_CASE.md`, `codebooks/public/seed_ai_formations.md`, and the relevant runtime/deployment documents before guessing study semantics. Canonical files outrank model memory; legacy repositories are archaeology only when current public-safe material is genuinely missing.

Rules:

- use canonical runners, records, provider protocols and storage adapters;
- preserve `source_url`, schema/version, evidence, uncertainty, abstention, review and provenance;
- distinguish descriptive computation from discourse-theoretical interpretation;
- inspect data quality and run compatibility before tuning prompts/models;
- never expose secrets or private runtime/codebook contents in logs or summaries;
- never silently switch local/cloud inference;
- current default analysis models are configurable and include `gemma4:12b`, `gemma4:31b-cloud`, and `gemma4:e2b`;
- distributed operation uses MongoDB + Redis + S3/CSC Allas through existing adapters;
- Roihu/Slurm, Laskin/cron and localhost are execution profiles, not separate scientific pipelines;
- agent-triggered work carries `caller=hermes-agent` and full model/config/run provenance;
- run repository quality gates before proposing merges.

See `docs/DEPLOYMENT_AND_HERMES.md` and the repository skill for operational details.