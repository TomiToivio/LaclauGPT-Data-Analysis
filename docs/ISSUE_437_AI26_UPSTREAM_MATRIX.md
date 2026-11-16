# Issue #437: AI26 upstream step compatibility and export QA

Audit baseline (2026-11-16):
- EP24 upstream `TomiToivio/LaclauGPT-Multimodal-Analysis` main: `858f383ddc1cf8e22f8d29a80646cebc1af2d173`.
- AI26 target `TomiToivio/LaclauGPT-Data-Analysis` main at start: `1077c42e1693a1f20bbe4f100c25607d9d065623`.
- Prior screening: [AI26_UPSTREAM_PORT_AUDIT.md](AI26_UPSTREAM_PORT_AUDIT.md), issue #382.
- Scientific source of truth: [Phase 1 paper](https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md). No prompts, taxonomy, codebooks, analytical claims, or schema were changed here.

## Specific recent upstream changes

| Source / class | AI26 disposition | Verification / follow-up |
| --- | --- | --- |
| EP24 #409 / commit `3724d0d`: truncated Step 8 JSON, budget escalation and schema-vs-length diagnostics | **Covered at provider-neutral AI26 boundary.** AI26 `llm/structured_output.py` already widens `num_predict` to a ceiling and distinguishes provider length stops from validation errors; tests in `tests/test_ai26_upstream_step7_step8_regressions.py` were merged as #436. Do not copy Step 8 prompts. | Recheck on Laskin with a bounded real AI26 sample; GitHub tests are not live evidence. |
| EP24 #410 / commit `858f383`: clear stale Step 8 SNA output on no-evidence retry | **Not a direct stage port.** Step 8 SNA is not part of locked AI26 Phase 1; canonical per-record postprocessing and explicit optional plugin stages use different identity/output lifecycles. | Audit retry persistence on Laskin for AI26 itself. Do not import SNA scientific steps by default. |
| EP24 #407 / commit `6fb8548`: offline export bundle integrity checking | **Adapted here** as `bundle_audit.py` for AI26 `write_research_bundle` layout, with synthetic regression tests. Checks JSONL parseability, CSV identity/header including BOM, duplicates, representation counts, Markdown report count, and SHA-256; emits *no source IDs/text*. | `python -m laclaugpt_data_analysis.bundle_audit /path/to/bundle --stem analysis`. Exit 0 = passes; exit 1 = inconsistencies. |
| EP24 #406 / commit `6653a87`: source LFS sample audit | **EP24/private-data specific.** AI26 has canonical source IDs and an upstream Collection handoff. No LFS sample import. | Collection source provenance should be evaluated separately during a real run. |
| EP24 Step 7/8 scientific outputs (DNA/SNA) and Roihu/SLURM | **Not ported to Phase 1.** Separate pipeline versions are addressed by #399. | Never silently change the Phase 1 research method. |

## Operator procedure (non-destructive)

1. Confirm deployment: `git rev-parse HEAD`, `python -c "import laclaugpt_data_analysis; print(laclaugpt_data_analysis.__file__)"`.
2. Run `scripts/run_ai26_laskin.sh --check`, `python -m laclaugpt_data_analysis.preflight`, and `python -m laclaugpt_data_analysis.deploy_drift --json`.
3. Use only an approved bounded test run. Capture counts and stage statuses, verify MongoDB/Redis handoff and provenance without sharing source text.
4. If a `write_research_bundle` export exists, run `python -m laclaugpt_data_analysis.bundle_audit /path/to/bundle --stem analysis` and record counts/hashes, not private source IDs.
5. File independent issues for reproducible failures, including deployed SHA, expected/observed behavior, sanitized logs and affected stage.

**Status:** This PR only delivers a scoped, safe upstream robustness port and updated compatibility matrix. No remote Laskin access or live end-to-end verification is claimed. Issue #437 must remain open until the full stage audit, CI and Laskin acceptance are complete.
