# AI26 Step 0–9 mapping and Laskin integration gate

Status: **design/integration audit**, not a new production orchestrator. Tracks [#341](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/issues/341). Date: 2026-10-15.

## Branch ownership and method

`main` is active Phase 2 infrastructure, `phase-1` preserves Phase 1. The locked AI26 Phase 1 theory/sampling/method in `LaclauGPT/paper/PHASE_1_PAPER.md` is not edited. Phase 2 network inference must remain opt-in/experimental. Do not modify Tomi-owned `laclaugpt/step_*.py` scientific method files: see `laclaugpt/HUMAN_PIPELINE.md`. This mapping is a **presentation/contract layer** over existing code, not an alternative pipeline.

## Audited components

- Existing production: `src/laclaugpt_data_analysis/distributed_worker.py`, `src/laclaugpt_data_analysis/stages/`, `src/laclaugpt_data_analysis/stage_contract.py`, `scripts/run_ai26_laskin.sh`, `scripts/run_ai26_laskin_analysis.sh`, public `config/projects/ai26.yaml`, `config/machines/laskin.yaml`, `config/execution/laskin-cron.yaml`.
- Existing readable scaffold: `laclaugpt/pipeline_runner.py` and `laclaugpt/step_01_preprocess.py` through `step_07_sna.py`. Some step implementations intentionally raise `NotImplementedError`; **do not advertise as production-ready**.
- Existing Collection handoff: canonical records in MongoDB, `handoff.status=ready`, stable `handoff_key` including source revision; Redis `laclaugpt:ai26:stream:analysis-ready` contains references, not payloads.
- Existing Visualization: `configs/projects/ai26.yaml`, provenance projection, RDF/DNA/SNA adapters. Dashboard flags for DNA/SNA/RDF are disabled in the default AI26 profile.

## Logical AI26 stages (do not confuse with current internal stage names)

| AI26 logical step | Existing implementation/scaffold | Input → output | Scientific ownership |
|---|---|---|---|
| 0 handoff/preflight | Collection handoff + distributed worker seed-ready | `source_url`, `handoff_key`, `revision`, `status`, `raw_capture` → eligible immutable source reference | infrastructure |
| 1 preprocess | `stages/preprocess.py`, `laclaugpt/step_01_preprocess.py` | original content, language, provenance → normalized text/evidence refs | descriptive |
| 2 optional image/frame | `stages/frame.py`, `laclaugpt/step_02_frame.py` | verified frame/image reference → frame evidence or explicit not-applicable | descriptive |
| 3 optional video | media staging/whole-video capability **requires verification** | verified video reference → video evidence or explicit not-applicable | descriptive |
| 4 summary | `stages/summary.py`, `laclaugpt/step_03_summary.py` | text and available media evidence → bounded summary | descriptive; mandatory |
| 5 postprocess | `stages/postprocess.py`, `laclaugpt/step_04_postprocess.py` | summary/evidence → structured descriptive fields | descriptive; mandatory |
| 6 Laclau/Palonen/imaginaries | `stages/laclau.py`, `laclaugpt/step_05_laclau.py`, project config | exact source evidence → claims, signifiers, formations, evidence-backed imaginaries and uncertainty | locked Phase 1 semantics; mandatory |
| 7 DNA | DNA statement coding and `laclaugpt/step_06_dna.py` | reviewable statements → provisional relations | **experimental Phase 2** |
| 8 SNA | network projection and `laclaugpt/step_07_sna.py` | provenance-linked edges → graph metrics | **experimental Phase 2** |
| 9 export | RDF/graph adapters, canonical Mongo record | `analysis`, `intermediate`, `provenance`, `review` → idempotent Visualization projection | infrastructure |

Required logical order: `0 → 1 → [2/3 if actual media] → 4 → 5 → 6 → 9`. Never treat absent media as a failure; never block Stage 9 on experimental 7/8. Existing source `source_url`, exact quotations, timestamps, provenance, human annotations and revisions are not overwritten by hypothetical model findings.

**Important:** this is a target numbering crosswalk, not a claim that the current production queue exposes ten independently callable entrypoints. #341 remains open until each step is runnable and tested, without creating another competing pipeline.

## Cross-repository contract findings

All three repositories' inspected `schemas/research-record.schema.json` have the same required top-level properties: `schema_version`, `source_url`, `raw_capture`, `source`, `content`, `intermediate`, `analysis`, `human_readable`, `provenance`, `review`, `legacy`. However, on 2026-10-15 **Analysis schema_version.const is 1.2.0; Collection and Visualization are 1.1.0**. Their strict JSON Schema validators therefore cannot all validate a single version unchanged. See [Collection #271](https://github.com/TomiToivio/LaclauGPT-Data-Collection/issues/271) and [Visualization #182](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/issues/182). This demonstrates a version contract mismatch, **not** a tested failure of the live Mongo/dashboard path. Do not silently change any version constant to conceal it.

Collection's stable handoff key is `hash(collection_id + source_url + revision)`; use it for idempotency. Mongo routing must be verified from actual private runtime before claiming that the dashboard consumes the same collection. Visualization's `docs/PROVENANCE_CONTRACT.md` specifies upstream safe run/config/prompt/model/codebook revisions and unknown fallbacks. Never conflate absent provenance with a scientifically inferred field.

## Laskin operator gates (nothing activated by this change)

1. Install current package in a private Laskin checkout as documented in `docs/AI26_LASKIN_ANALYSIS.md`. Use the existing `scripts/run_ai26_laskin.sh`; **do not deploy the human-readable scaffold as a competing worker**.
2. Run `python tools/check_ai26_contracts.py --collection ../LaclauGPT-Data-Collection --visualization ../LaclauGPT-Data-Visualization` on adjacent checked-out repos. This fails on the current verified 1.2.0/1.1.0 strict-version mismatch.
3. Use `scripts/run_ai26_laskin.sh --check` after provisioning Laskin private config, Ollama and dependencies. This is not proof of runtime correctness unless exit codes and logs are checked.
4. Run bounded small-sample manual pilot, retain source IDs and stage statuses, review output against source evidence, and check Collection input/Visualization display with the same real Mongo DB and collection settings.
5. Only after schema resolution, integration tests, representative human review and sign-off, enable staggered cron using the documented installer. No cron activation or production store migration is part of this PR.

## Remaining acceptance work

- Confirm whole-video stage 3 evidence semantics, step-by-step entrypoints, stage registry, effective prompt render/validation, prompt/schema hash, explicit not-applicable status and retries.
- Add fixture-driven cross-repo producer/consumer tests for multimodal, text-only, multilingual and missing provenance. Confirm stable Mongo collection names and identity across private runtime settings.
- Demonstrate restart-safe/idempotent bounded pilot on Laskin and actual Visualization consumption. Preserve EP24/Roihu references.
