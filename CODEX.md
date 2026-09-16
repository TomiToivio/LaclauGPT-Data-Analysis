# Codex operation

Codex and other coding agents must follow `AGENTS.md` and `skills/laclaugpt-data-analysis/SKILL.md`.

Treat this repository as academic research software, not only an application codebase. You may act as analysis engineer, computational social scientist, research assistant, method auditor and deployment operator, but all changes must stay inside the canonical Analysis architecture.

Before changing AI26 behavior, read `docs/AI26_REFERENCE_CASE.md`, `codebooks/public/seed_ai_formations.md`, and the relevant runtime/deployment documentation. Do not reconstruct codebooks, run settings or deployment assumptions from model memory when repository files exist.

Keep scientific and infrastructure concerns separated: one analysis pipeline should run under localhost, Roihu/Slurm, Laskin/cron or agent execution with the same canonical record/result semantics. Use existing MongoDB, Redis and S3/CSC Allas adapters for distributed work. Preserve `source_url`, evidence, uncertainty, review and provenance.

Before editing LLM scientific instructions, read `docs/PROMPT_LIBRARY.md` and the versioned files under `src/laclaugpt_data_analysis/prompts/`. Reuse canonical prompt IDs/versions instead of inventing or reconstructing prompts in Python. Any prompt wording/format change that may alter model behavior gets a new version and must retain exact resource/rendered hashes in provenance.

Do not hard-code provider calls into scientific modules, expose secrets, invent CSC/runtime values, commit private corpora/codebooks, or silently change model/provider semantics. Add synthetic tests and run configured lint/type/test/public-tree gates before proposing a merge.