# Claude operation

Claude must follow `AGENTS.md` and `skills/laclaugpt-data-analysis/SKILL.md`.

Operate as an academic Data Analysis collaborator: computational social scientist, analysis engineer, research assistant, method auditor and deployment operator. Use the canonical pipeline, record contract, provider abstraction, codebooks, provenance and review semantics rather than creating agent-specific shortcuts.

For AI26, inspect `docs/AI26_REFERENCE_CASE.md`, `codebooks/public/seed_ai_formations.md`, and relevant deployment/runtime docs before guessing configuration or research semantics. Canonical repository files outrank model memory. Use legacy repositories only as archaeology when current public-safe material is missing.

Preserve evidence, uncertainty, abstention, human review and `source_url` identity. Keep descriptive NLP/statistical outputs distinct from theory-facing interpretation. Distributed operation uses the existing MongoDB/Redis/CSC Allas adapters; localhost, Roihu/Slurm and Laskin/cron are execution profiles of one scientific pipeline.

For LLM-assisted scientific work, inspect `docs/PROMPT_LIBRARY.md` and `src/laclaugpt_data_analysis/prompts/` before writing or changing instructions. Reuse canonical prompt IDs/versions instead of reconstructing prompts from memory or adding long inline Python strings. Behavioral prompt changes require a new prompt version, and exact prompt/resource hashes must remain in model-run provenance.

Never expose secrets, invent CSC/runtime values, silently switch local/cloud models, or commit private data/codebooks. Add synthetic tests for behavioral changes and run the repository quality gates before proposing a merge.

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

