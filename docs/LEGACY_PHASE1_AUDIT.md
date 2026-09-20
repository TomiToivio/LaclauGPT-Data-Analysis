# Phase 1 legacy-code audit and quarantine

Status: **Phase 1 Step 11 / issue #224**

This inventory is intentionally conservative. Step 11 is an audit and quarantine pass, not a capability-reactivation or deletion bundle. Legacy files remain available as archaeology unless replacement behavior and dependency removal are both proven.

## Rules

- **KEEP / QUARANTINE**: retain as compatibility or scientific-method reference. Active runtime code must not import it.
- **ADAPT / CANONICALIZED**: important behavior has a canonical home. Keep the legacy artifact quarantined until regression coverage proves the replacement is sufficient for the relevant study.
- **DELETE AFTER REPLACEMENT**: deletion is permitted only after active imports/entry points are absent and the replacement has regression coverage. This audit does **not** delete these files.
- Any unproven dependency automatically falls back to **KEEP / QUARANTINE**.

The active Phase 1 runtime lives under `src/laclaugpt_data_analysis/` and the `[project.scripts]` entry points in `pyproject.toml`. The top-level `laclaugpt/` directory is treated as legacy/compatibility space unless a file is explicitly migrated.

## Inventory

| Legacy artifact | Classification | Canonical replacement / evidence | Deletion gate |
|---|---|---|---|
| `laclaugpt/puhti_frame.py` | KEEP / QUARANTINE | `docs/MULTIMODAL_MIGRATION.md`; canonical multimodal/frame contracts; versioned EP24 frame prompt in `src/laclaugpt_data_analysis/prompts/ep24/frame_analysis_v2.md` | Retain until an EP24 regression fixture proves timestamped visual-observation parity end to end. |
| `laclaugpt/puhti_summary.py` | KEEP / QUARANTINE | canonical staged context plus `prompts/ep24/summary_analysis_v2.md` | Retain until EP24 regression fixtures prove multimodal-summary obligations and provenance. |
| `laclaugpt/puhti_populism.py` | KEEP / QUARANTINE | canonical Laclau stage plus `prompts/ep24/laclau_analysis_v2.md` | Retain until EP24 output-contract parity is proven for representative FI/PL fixtures. |
| `laclaugpt/puhti_preprocess.py` | ADAPT / CANONICALIZED, still quarantined | `docs/MULTIMODAL_MIGRATION.md` maps frame sampling, ASR/OCR adapters and resumable preprocessing into canonical multimodal/runtime contracts | Candidate for later deletion only after cache/resume and media-preprocessing regressions cover historical inputs. |
| `laclaugpt/puhti_postprocess.py` | ADAPT / CANONICALIZED, still quarantined | canonical postprocessing / research-record export paths; legacy prompt preserved under `docs/legacy_ep24_prompts/` | Candidate for later deletion only after EP24 compatibility-export regression coverage proves the old consumer contract is no longer required. |
| `docs/legacy_ep24_prompts/*` | KEEP / QUARANTINE | immutable methodological archaeology used to verify canonical prompt obligations | Do not delete while EP24 reproducibility depends on comparison with the historical prompt contracts. |
| `docs/EP24_LEGACY_PROMPTS.md` | KEEP / QUARANTINE | provenance/index for historical scientific-method resources | Keep with the archived prompt set. |
| `docs/MULTIMODAL_MIGRATION.md` | KEEP | migration decision record | Not a deletion candidate. |
| `laclaugpt/laclaugpt_preprocess.py`, `laclaugpt/laclaugpt_process.py`, `laclaugpt/laclaugpt_postprocess.py`, `laclaugpt/laclaugpt_summary.py`, `laclaugpt/laclaugpt_discourse.py` | ADAPT / CANONICALIZED, still quarantined | staged canonical runner, context envelope, prompt library, plugin runtime and canonical record model under `src/laclaugpt_data_analysis/` | Review individually only after regression coverage shows no study-specific behavior remains unique to the script. |
| `laclaugpt/laclaugpt_mongo.py`, `laclaugpt/laclaugpt_redis.py`, `laclaugpt/laclaugpt_index.py`, `laclaugpt/laclaugpt_query.py`, `laclaugpt/laclaugpt_seed_graph.py`, `laclaugpt/laclaugpt_ontology.py` | ADAPT / CANONICALIZED, still quarantined | storage-neutral canonical stores, task queue, MongoDB/RAG/RDF/plugin modules under `src/laclaugpt_data_analysis/` | Delete only after deployment and persistence regressions establish that no operational workflow calls these scripts directly. |
| `laclaugpt/ai26_rss.py`, `laclaugpt/laclaugpt_collect_rss.py`, `laclaugpt/laclaugpt_validate_rss.py`, `laclaugpt/rss_test.py` | KEEP / QUARANTINE | collection behavior belongs in Data Collection; these copies are repository archaeology | Move/delete only after cross-repository ownership and any historical AI26 workflow dependency are proven. |
| `laclaugpt/laclaugpt_geocode.py`, `laclaugpt/laclaugpt_report.py` | KEEP / QUARANTINE | no sufficiently proven one-for-one canonical replacement established by this audit | Retain. |
| `laclaugpt/requirements.txt` | DELETE AFTER REPLACEMENT | dependency authority is `pyproject.toml` plus `requirements/` | Delete only after confirming no external deployment script installs this legacy file. |
| `laclaugpt/README.md`, `laclaugpt/PROMPT_*.md` | KEEP / QUARANTINE | historical design/prompt reference; canonical prompt resources live under `src/laclaugpt_data_analysis/prompts/` | Retain while useful for archaeology; never load them implicitly as active Phase 1 prompts. |

## Active-dependency audit

Issue #224 requires deletion candidates to have no active import or entry-point dependency. The accompanying `tests/test_legacy_quarantine.py` enforces two boundaries:

1. Python modules under `src/laclaugpt_data_analysis/` may not import any `puhti_*` module.
2. `pyproject.toml` console-script entry points may not target `puhti_*` or the legacy top-level `laclaugpt/` scripts.

Repository search on the Step 11 implementation found references to the `puhti_*` names in migration documentation, archived prompt resources and legacy scripts themselves, but not active `src/` imports.

## Existing regression evidence

Important behavior is already covered in canonical tests before any deletion is contemplated:

- prompt resource/version behavior: `tests/test_prompt_library.py`, `tests/test_prompt_architecture.py`;
- plugin/legacy-adapter behavior: `tests/test_plugin_pipeline.py`;
- staged canonical execution and prior-stage context: `tests/test_staging.py`, `tests/test_stage_contract.py`;
- Phase 1 text/shadow compatibility: `tests/test_phase1_text_runtime.py`, `tests/test_phase1_shadow_bridge.py`;
- social-semiotic pre-analysis: `tests/test_social_semiotic_preanalysis.py`;
- persistence/reprocessing compatibility: `tests/test_reprocessing.py`, `tests/test_storage.py`, `tests/test_phase1_persistence_failures.py`.

These tests justify adaptation/quarantine classifications, but they do **not** automatically justify deleting the historical scripts. Where end-to-end EP24 parity or external operational dependencies remain unproven, the file stays quarantined.

## Outcome

Step 11 establishes a one-way boundary: legacy artifacts may inform tests, migration notes and explicit compatibility work, but active Phase 1 code must not depend on them. No capabilities are reactivated here, and no legacy implementation is deleted merely because a newer implementation exists.
