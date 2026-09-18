# Codex operation

Codex and other coding agents must follow `AGENTS.md` and `skills/laclaugpt-data-analysis/SKILL.md`.

Treat this repository as academic research software, not only an application codebase. You may act as analysis engineer, computational social scientist, research assistant, method auditor and deployment operator, but all changes must stay inside the canonical Analysis architecture.

Before changing AI26 behavior, read `docs/AI26_REFERENCE_CASE.md`, `codebooks/public/seed_ai_formations.md`, and the relevant runtime/deployment documentation. Do not reconstruct codebooks, run settings or deployment assumptions from model memory when repository files exist.

Keep scientific and infrastructure concerns separated: one analysis pipeline should run under localhost, Roihu/Slurm, Laskin/cron or agent execution with the same canonical record/result semantics. Use existing MongoDB, Redis and S3/CSC Allas adapters for distributed work. Preserve `source_url`, evidence, uncertainty, review and provenance.

Before editing LLM scientific instructions, read `docs/PROMPT_LIBRARY.md` and the versioned files under `src/laclaugpt_data_analysis/prompts/`. Reuse canonical prompt IDs/versions instead of inventing or reconstructing prompts in Python. Any prompt wording/format change that may alter model behavior gets a new version and must retain exact resource/rendered hashes in provenance.

Do not hard-code provider calls into scientific modules, expose secrets, invent CSC/runtime values, commit private corpora/codebooks, or silently change model/provider semantics. Add synthetic tests and run configured lint/type/test/public-tree gates before proposing a merge.

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

