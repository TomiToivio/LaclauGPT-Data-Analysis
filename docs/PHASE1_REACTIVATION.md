# Phase 1 reactivation runtime

Phase 1 is developed on the phase-1 branch while main/phase-0 remain the stable production line.

The reactivation path is intentionally additive:

1. copy/adapt a Phase 0 Mongo-shaped document into a canonical shadow record;
2. optionally run provider-free canonical preprocessing;
3. explicitly enable Phase 1 text summary;
4. separately enable Laclaudian discourse analysis;
5. persist only under the top-level phase1 namespace;
6. export a Visualization handoff that excludes raw Phase 0 and legacy/private fields.

## Safety defaults

Both Phase 1 execution flags default off:

- LACLAUGPT_PHASE1_ENABLED=0
- LACLAUGPT_PHASE1_DISCOURSE_ENABLED=0
- LACLAUGPT_PHASE1_ALLOW_CLOUD_FALLBACK=0

Optional settings:

- LACLAUGPT_PHASE1_MODEL
- LACLAUGPT_PHASE1_PROMPT_VERSION
- LACLAUGPT_PHASE1_PROJECT_PROFILE

The stable laclaugpt/laclaugpt_process.py Phase 0 orchestrator is not imported or modified by this runtime.

## Shadow export

Use copied/sanitized Phase 0 JSONL, never the live queue:

    laclaugpt-phase1-shadow copied-phase0.jsonl --preprocess

Outputs default to data/exports. Malformed input rows are reported in a separate diagnostics JSONL.

## Activation and rollback

For a bounded Laskin comparison, set LACLAUGPT_PHASE1_ENABLED=1 only in the Phase 1 worker/process environment. Enable discourse with LACLAUGPT_PHASE1_DISCOURSE_ENABLED=1 after summary-only validation.

Rollback is immediate: unset both flags. Phase 0 fields are never overwritten. If Phase 1 persistence has been used, the isolated phase1 namespace can be ignored or removed without migrating Phase 0.

A real Laskin bounded run remains an operator/integration validation step and is intentionally not part of ordinary CI.
