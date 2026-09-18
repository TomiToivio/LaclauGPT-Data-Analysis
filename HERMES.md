# Hermes operation

Hermes follows `AGENTS.md` and `skills/laclaugpt-data-analysis/SKILL.md` as the authoritative contract. It is an academic research agent operating the same canonical Analysis APIs as researchers, schedulers and other coding agents.

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

## TOMI-LOCKED

Anything marked `TOMI-LOCKED` is a human-controlled invariant.

Agents MUST NOT modify, refactor, rename, migrate, remove, reinterpret, or change the semantics of a TOMI-LOCKED element.

This includes indirect changes whose effect would alter a locked interface, data format, workflow, behavior, assumption, prompt, schema, configuration, or documented contract.

When an agent encounters `TOMI-LOCKED`:

1. Preserve the marked element exactly unless Tomi's current instruction explicitly authorizes changing that specific locked element.
2. Do not bypass the lock through dependent code, schemas, serializers, migrations, tests, prompts, documentation, interfaces, configuration, or compatibility layers.
3. Do not remove the `TOMI-LOCKED` marker during cleanup, refactoring, migration, modernization, or documentation work.
4. Broad instructions such as "refactor", "modernize", "fix everything", "make CI green", "update the pipeline", or similar do NOT override a lock.
5. If a requested task conflicts with a locked element, preserve the lock, complete any non-conflicting work that is safe to do, and clearly report the conflict.
6. If Tomi explicitly authorizes a change to a specific locked element, that element may be changed, but the `TOMI-LOCKED` marker remains unless Tomi explicitly asks to remove the lock itself.

Only explicit authorization from Tomi for the specific locked element overrides the lock.

Marker examples:

```python
# TOMI-LOCKED
# Do not modify without explicit approval from Tomi.
```

```markdown
<!-- TOMI-LOCKED -->
```

```yaml
# TOMI-LOCKED
```

The marker is intentionally grep-friendly:

```bash
grep -R "TOMI-LOCKED" .
```

