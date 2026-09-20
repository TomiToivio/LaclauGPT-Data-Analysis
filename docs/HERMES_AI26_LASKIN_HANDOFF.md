# Hermes handoff: AI26 Phase 1 Analysis on Laskin

This is the host-execution handoff for issue #274. The repository-side Phase 1 AI26 Laskin runtime is already implemented. Hermes should bring up, verify and operate that runtime on Laskin rather than create a parallel engine.

## Already prepared in Git

- `scripts/run_ai26_laskin.sh`: bounded, locked, incremental worker entry point with preflight support.
- `scripts/install_ai26_laskin_cron.sh`: refreshes the frozen run, verifies a cron-equivalent cycle, installs a single tagged hourly entry, then runs preflight.
- `docs/AI26_LASKIN_ANALYSIS.md`: canonical operator guide.
- Canonical Collection ingestion, retry/dead-letter behavior, Mongo durability, Redis coordination, multimodal staging and provenance.
- AI26 runtime policy reads the configured study date boundary rather than hard-coding it.
- Mongo-backed idempotent 24h reports and direct Analysis -> Visualization handoff.
- `src/laclaugpt_data_analysis/phase1_handoff.py` provides the public-safe Visualization projection.

Do not introduce a second AI26-only analysis engine or browser logic.

## Hermes mission on Laskin

1. Read `AGENTS.md`, `HERMES.md`, `docs/AI26_LASKIN_ANALYSIS.md`, issue #274, and the current AI26 project/machine/execution configs before changing anything.
2. Verify the public checkout and authorized private root. Do not discard unrelated local work and do not copy private overlays into Git.
3. Update/install the current repository and required extras according to the runbook.
4. Run public tests/lint before live work:

```bash
pytest -q
ruff check .
```

5. Run the exact unattended preflight:

```bash
./scripts/run_ai26_laskin.sh --check
```

The check must claim no work and must not print credentials.

6. Confirm the configured local model endpoint/model are available according to the machine profile. Do not silently switch to cloud routing unless the authorized runtime configuration explicitly enables it.
7. Execute one bounded debug cycle:

```bash
./scripts/run_ai26_laskin.sh --debug --once
```

8. Verify a synthetic/public-safe canonical Collection item can move through:
   - schema/version validation;
   - descriptive preprocessing;
   - configured LaclauGPT Phase 1 analysis;
   - optional stages only when enabled;
   - durable persistence with provenance/fingerprints;
   - 24h report input;
   - Visualization-ready output with no manual conversion.
9. Verify failure isolation using only safe test inputs: one malformed/incompatible item must become retryable/quarantined without blocking unrelated work.
10. Re-run the same bounded cycle and verify duplicate/idempotent behavior and cache/fingerprint logic.
11. Verify the AI26 configured date boundary is applied from configuration with the repository's documented strict-after semantics.
12. Run or verify the idempotent 24h report path and confirm grouping/filter dimensions remain bounded.
13. Only after the manual cycle passes, install/update the cron entry using:

```bash
./scripts/install_ai26_laskin_cron.sh
```

14. Confirm logs/status are operational and free of secrets.

## Cross-repo exit check

Use a real synthetic/public-safe Collection record from the shared `ai26` namespace. Analysis must preserve stable `source_url`, study/collection identity and evidence provenance, then expose the result through the canonical Visualization handoff (`laclaugpt-analysis-visualization-v1`) without a bespoke export transform.

Verify the Visualization Laskin deployment can see the new result unchanged.

## Research-integrity checks

Keep source evidence, descriptive pre-analysis, model-generated candidates and researcher-authored categories distinguishable. Do not promote candidate formations/signifiers/relations into researcher truth. Preserve uncertainty/abstention and review state.

## When to change code

Only change public code if the live deployment reveals a reproducible generic defect. Add a synthetic regression test and keep Phase 0 isolated.

## Completion evidence for issue #274

Post only sanitized evidence: commit SHA, preflight result, bounded processed/failed/retried counts, idempotence result, report result, effective schema/handoff versions, and confirmation that Visualization consumed the result unchanged. Do not post prompts/codebooks from private overlays, research rows, endpoints, tokens or credentials.
