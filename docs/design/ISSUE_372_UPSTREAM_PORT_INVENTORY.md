# Issue #372 — upstream port inventory (Multimodal → AI26 Data-Analysis)

**Scope.** Every merged change in `LaclauGPT-Multimodal-Analysis` (MM) screened against
`LaclauGPT-Data-Analysis` (DA), with a disposition that can be checked. The AI26 Phase 1
methodology, codebooks, prompts and the research-record schema are **contracts**: this
inventory treats them as read-only and says so wherever a change would have needed them.

**Method.** The twelve PRs named in #372 were read in full (body, diff, tests). The remaining
merged history was screened by title, changed-file set and, for every behavioural candidate,
the diff itself. Each verdict is one of:

* **ported** — the behaviour was missing in DA and this PR adds it, with the test that proves it;
* **already present** — DA already does it; the row cites the file and, where one exists, the test;
* **not applicable** — the change is EP24-only, SLURM/Roihu-only, or assumes a data shape DA does not have;
* **deferred** — real, but out of scope for a Phase 1 port; the row says what would be needed.

A verdict is about **behaviour**, never about the diff: several upstream files port cleanly in
shape and not in meaning, and several DA files already implement the same guarantee by a
different mechanism.

**Totals** — 226 merged PRs, all accounted for: 59 dispositioned
individually (no PR twice) and 167 as seven clusters, with no overlap and none missing.
Of the individually dispositioned rows: **8 ported**,
**29 already present**, **21 not
applicable**, **1 deferred**. One further PR named in the issue, #296,
was closed unmerged and is dispositioned separately at the end.

---

## A note on the earlier audit note in this branch

Commit `a8e6eb8` carried `docs/AI26_UPSTREAM_PORT_AUDIT.md`, which concluded that #287's defect
does not exist in AI26 because durable identity is Collection's immutable `handoff_key`. Half of
that is right: the key covers the source revision. The defect is that `DurableTaskStore.has_result`
answered **presence only** — `return idempotency_key in self.results` in memory, `SELECT 1` in
SQLite, `find_one` on the key in Mongo. A run with a different model, prompt version, `num_ctx` or
`num_predict` therefore reported every analysed record as a *completed duplicate* and never
re-analysed it, silently. That is #287's class, so this PR ports it (class B) rather than
documenting it away. The trade-off the earlier note names — automatic re-analysis on every prompt
tweak — is kept in check by the compatibility rule in class B: a row written before the guard has
no fingerprint and keeps resuming.

---

### A. Empty or truncated model output: retry, then fail fast

| Upstream PR | Title | Merged | Verdict | Destination in DA | Evidence |
| --- | --- | --- | --- | --- | --- |
| [#274](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/274) | Step 4 #236: retry HTTP-200 empty Ollama summaries | 2026-10-12 | **ported** | `llm/ollama.py` `complete_with_empty_retry`; `llm/multimodal.py`; `llm/structured_output.py` empty-answer guard | `tests/test_issue_372_empty_response_retry.py` (7 tests): blank→retry→answer, exhaustion raises `LLMEmptyResponseError`, truncation is not retried |
| [#280](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/280) | Fix Step 6 JSON truncation | 2026-10-13 | already present | `llm/structured_output.py` 4096→8192→16384 ladder ending in `LLMTruncationError` | `tests/test_issue_280_output_truncation.py` |
| [#167](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/167) | fix(postprocess): normalize Step 5 outputs before discourse analysis (#157) | 2026-10-02 | already present | `llm/structured_output.py` `_coerce_single_string_lists` normalises unambiguous scalar→list shapes before Pydantic validation and leaves real errors to raise | `tests/test_issue_100_string_list_coercion.py` |
| [#233](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/233) | Detect and recover degenerate Qwen3-VL Step 3 output without losing upstream data | 2026-10-10 | not applicable | vLLM video output; DA has no vLLM path | read: `experiments/vllm_video_test.py` diff — degenerate-output recovery is video-generator specific |
| [#251](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/251) | Fix Step 3 runaway video descriptions and status-only responses | 2026-10-11 | not applicable | vLLM video prompt shaping (runaway descriptions, status-only replies) | read: `experiments/vllm_video_test.py` diff |
| [#247](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/247) | Fix Step 1 duplicate Cyrillic OCR and silent empty-ASR cache reuse | 2026-10-11 | not applicable | ASR/OCR cache in EP24 Step 1; AI26 has no ASR stage | read: `roihu_preprocess.py` diff; the AI26 form of the class is now covered by the empty-answer guard |
| [#169](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/169) | fix(step1): cache-hit output is schema-equivalent to a fresh run (#168) | 2026-10-02 | already present (adapted) | `FrozenRunManifest` schema + `CanonicalRecord.model_validate` on read; one canonical record shape for fresh and stored results | `distributed_worker.py` `validate_files` / `MongoCollectionHandoff.resolve` |

### B. Resume and idempotency bound to the effective settings

| Upstream PR | Title | Merged | Verdict | Destination in DA | Evidence |
| --- | --- | --- | --- | --- | --- |
| [#287](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/287) | Bind Step 6/7 resume hashes to effective generation settings (#239 #240 #241) | 2026-10-14 | **ported** (adapted) | `llm/base.py` `generation_fingerprint`; `task_queue.py` `has_result`/`write_result` fingerprint in all three stores; `distributed_worker.py` `ai26_generation_fingerprint` + `has_current_result` | `tests/test_issue_372_resume_fingerprint.py` (13 tests): changed model/mode/option/prompt is a cache miss that re-analyses and logs `resume_invalidated`; matching fingerprint is a duplicate; legacy rows without a fingerprint keep resuming; SQLite table upgrades in place |
| [#179](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/179) | Harden EP24 Step 6 resume, abstention and legacy compatibility | 2026-10-02 | already present | `stages/proposals.py` abstention fields; `AI26TaskWorker` terminal failure + dead-letter instead of a half-written row | `distributed_worker.py` `run_once`; `tests/test_distributed_worker.py` |
| [#267](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/267) | Fix Step 2 SQLite checkpoint failure on nested MongoDB values | 2026-10-11 | already present (adapted) | `task_queue.py` persists JSON with `default=str`; no typed SQLite columns for nested Mongo values | `write_result` in all three stores |
| [#165](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/165) | fix(summary): make Step 4 cumulative, restart-safe and Mongo-aware (#154) | 2026-10-02 | already present (adapted) | append-only stage trail `append_stage`; durable result per handoff key | `stages/shared.py` `append_stage`; `tests/test_canonical_pipeline_v2.py` |
| [#252](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/252) | Add safe EP24 archive-and-restart workflow for Roihu | 2026-10-11 | not applicable | archive-and-restart workflow for Roihu scratch space | read: PR body — AI26 recovery is a bounded cycle, no archive step |

### C. Structured-output validation that fails loudly

| Upstream PR | Title | Merged | Verdict | Destination in DA | Evidence |
| --- | --- | --- | --- | --- | --- |
| [#205](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/205) | Implement issue #204 shared OK / REPROCESS / DELETE quality gate | 2026-10-02 | not applicable | EP24 OK/REPROCESS/DELETE video quality gate | read: PR body — no video quality routing in AI26 |
| [#206](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/206) | fix(quality): stop reading ordinary prose as a DELETE verdict (#204) | 2026-10-03 | not applicable | same quality gate, prose read as DELETE | read: PR body |
| [#208](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/208) | fix(quality): unrecognised status must not abort Step 5 + routing-gate tests (#204) | 2026-10-03 | not applicable | same quality gate, unrecognised status must not abort a stage | read: PR body |
| [#186](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/186) | fix(ep24): Step 6 emits the bare element so abstention survives to RDF (#180) | 2026-10-02 | not applicable | EP24 Step 6 bare-element RDF projection | read: PR body — AI26 has no EP24 element contract |

### D. Model and dependency preflight

| Upstream PR | Title | Merged | Verdict | Destination in DA | Evidence |
| --- | --- | --- | --- | --- | --- |
| [#292](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/292) | Fix Step 3 preflight for missing pymongo and redis | 2026-10-14 | already present (+#373) | `preflight.py` `_check_mongodb` / `_check_redis` report `pymongo_not_installed` / `redis_not_installed` without crashing; PR #373 makes a configured-but-unproven backend fail closed | `preflight.py`; `tests/test_issue_372_preflight.py` (in #373) |
| [#293](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/293) | test: update Step 3 preflight dependency assertion after Mongo/Redis checks | 2026-10-15 | already present (+#373) | same checks with regression coverage | `tests/test_issue_372_preflight.py` (in #373) |
| [#215](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/215) | Diagnose Step 2 MongoDB authorization failures clearly | 2026-10-09 | already present | `preflight.py` reports the exception *class* for a Mongo failure and never the URI | `_check_mongodb`; `sanitize_url` |
| [#158](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/158) | fix(cli): defer DNA/SNA runtime imports for minimal --help (#152) | 2026-10-02 | already present | `ai26.py` imports stage modules lazily and reports an unimportable one instead of crashing `--help`; `llm/` imports `ollama` lazily | `ai26.py` `_first_docstring_line`; `tests/test_issue_341_ai26_cli.py` |
| [#214](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/214) | Fix Step 2 Roihu MongoDB-disabled orchestrator crash | 2026-10-09 | already present | `MongoCollectionHandoff` refuses to construct without `mongo_url`, and `preflight.py` reports the backend as unconfigured rather than crashing | `distributed_worker.py`; `preflight.py` `_check_mongodb` |
| [#255](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/255) | Allow Step 1 metadata tests to collect without OpenCV | 2026-10-11 | already present | optional multimodal imports are lazy, so the suite and the text path collect without OpenCV | `stages/runner.py` lazy `FrameAwareProvider` import |
| [#232](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/232) | Fix Roihu Step 3 missing qwen_vl_utils before Qwen3-VL inference | 2026-10-10 | not applicable | `qwen_vl_utils` / Qwen3-VL runtime | read: PR body |
| [#217](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/217) | Auto-pull missing Ollama model on Roihu | 2026-10-09 | not applicable | auto-pull a missing Ollama model on Roihu | read: PR body — Laskin's wrapper fails with the `ollama pull` command instead |
| [#221](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/221) | Fix Step 3 rclone preflight lookup after Allas initialization | 2026-10-09 | not applicable | `rclone`/Allas preflight | read: PR body |
| [#212](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/212) | Fix Step 3 Roihu preflight: install and expose rclone | 2026-10-09 | not applicable | install and expose `rclone` on Roihu | read: PR body |

**Gap found while auditing #292/#293.** DA's preflight reported the store drivers correctly, and PR #373 closes the remaining "configured but unproven" hole for MongoDB/Redis. The provider was different: ``OllamaProvider`` imports ``ollama`` lazily, so a missing package surfaced *after* a task had been claimed. ``enforce_local_model`` now checks it when the worker is built — before the first claim — and ``tests/test_issue_372_worker_preflight.py`` pins all three branches.

### E. Evidence and prompt budgeting

| Upstream PR | Title | Merged | Verdict | Destination in DA | Evidence |
| --- | --- | --- | --- | --- | --- |
| [#259](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/259) | feat(#241): shared Steps 4-8 context budget and prompt contract | 2026-10-11 | **ported** | `prompt_budget.py` (new): `Section`, `FieldReport`, `Packet`, `resolve_budget`, `allocate`, `summarise` | `tests/test_issue_372_prompt_budget.py` (12 tests) |
| [#262](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/262) | feat(#236): reserve context for the answer, and log the model-visible size per field | 2026-10-11 | **ported** | `context_envelope.py` bounded render; `stages/shared.py` `render_prompt` logs the model-visible size before the call; report stored as `prompt_budget` | `tests/test_issue_372_prompt_budget.py::test_the_report_records_the_model_visible_size_per_section` |
| [#285](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/285) | Static review: tighten Step 8 source grounding and prompt-budget invariants (#238 #241) | 2026-10-14 | **ported** (invariant only) | `prompt_budget.allocate` guarantees the rendered text is within the budget, omitted markers included | `tests/test_issue_372_prompt_budget.py::test_rendered_text_never_exceeds_the_model_visible_budget` |
| [#230](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/230) | Fix Step 2 Ollama context overflow from oversized Mongo RAG memory | 2026-10-09 | **ported** (class) | oversized retrieved context can no longer push the task out of the window: `current_source`/`previous_analysis` are capped and the task has the highest priority | `tests/test_issue_372_prompt_budget.py::test_the_task_is_what_survives_when_the_record_does_not_fit` |
| [#246](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/246) | Fix false DELETE classifications and frame prompt budget overrun | 2026-10-11 | **ported** (class) | same envelope budget; the EP24 frame prompt itself stays upstream | as above |
| [#256](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/256) | feat(#241): shared model-visible prompt/context contract for Steps 4-8 | 2026-10-11 | already present | `stages/registry.json` + `ai26.py validate-contract`: the prompt contract is machine-readable and validated offline | `tests/test_issue_341_validate_contract.py` |
| [#294](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/294) | Consolidate the EP24 Steps 4-8 prompt/context builders into one contract (#241) | 2026-10-15 | already present | one `PromptEnvelope` for every stage; no four competing builders to consolidate | `context_envelope.py`; `tests/test_prompt_architecture.py` |
| [#242](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/242) | Step 5: only send task-relevant evidence to Ollama | 2026-10-10 | already present (adapted) | layered envelope keeps memory/RAG separate from source evidence with explicit trust roles | `context_envelope.py`; `tests/test_analysis_context.py` |
| [#244](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/244) | Step 4: bounded, provenance-labelled multimodal evidence (#236) | 2026-10-10 | already present (adapted) | every envelope fragment carries provenance labels | `PromptEnvelope.provenance_snapshot` |
| [#257](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/257) | EP24 Steps 6–8: source-first bounded evidence packets and safe rerun contract (#238–#241) | 2026-10-11 | not applicable | EP24 Steps 6-8 evidence packets | read: PR body |
| [#258](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/258) | feat(ep24): shared Steps 4-8 prompt/context contract; Step 8 audit parity (#241, #238) | 2026-10-11 | not applicable | EP24 Step 8 audit parity | read: PR body |

**Two different budgets, deliberately.** ``context_profiles.max_context_chars`` bounds the *retrieved context* that is assembled before the envelope exists; this PR adds the *model-visible prompt* budget, which nothing bounded. They compose: retrieval stays as it was, and the envelope can no longer overflow the context window even when a record or a previous stage output is large.

### F. Provenance and error logging

| Upstream PR | Title | Merged | Verdict | Destination in DA | Evidence |
| --- | --- | --- | --- | --- | --- |
| [#290](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/290) | Clarify Step 6–8 evidence provenance and log dropped packet fields | 2026-10-14 | already present (stronger) | `stages/evidence.py`: the quote is located in the original source with character offsets and an `exact` flag; an inexact quote is recorded, never dropped | `tests/test_evidence_source_grounding.py` |
| [#137](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/137) | fix(ep24): classify asr_/preprocess_ output as derived, not source facts (#129) | 2026-10-02 | already present | `Evidence.kind = llm_proposed_source_evidence` + offsets make derived text unusable as source proof | `stages/evidence.py`; `canonical.py` `Evidence` |
| [#261](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/261) | Step 8: reject SNA edges without verbatim source evidence (#238) | 2026-10-11 | deferred | Phase 2 SNA (`sna/`) has no verbatim-evidence gate on edges | read: `sna/graph.py` — Phase 2 is experimental and out of a Phase 1 port; needs its own issue |
| [#127](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/127) | fix(ep24): load authoritative URLs nested under provenance.sources | 2026-10-02 | not applicable | EP24 codebook workbooks with nested `provenance.sources` | read: `roihu_codebooks.py` diff |
| [#222](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/222) | Make EP24 Steps 1–9 observable: predictable Slurm logs and human review CSVs | 2026-10-09 | already present (adapted) | one cron log path + per-cycle status JSON + `deploy_drift` | `scripts/run_ai26_laskin.sh`; `tests/test_issue_353_deploy_drift.py` |
| [#216](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/216) | Make all EP24 stages print and log analysis outputs while retaining CSV checkpoints | 2026-10-09 | not applicable | print-and-log for CSV checkpoint stages | read: PR body |
| [#225](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/225) | Explain Step 1 empty Mongo collection and align default dataset with Step 0 | 2026-10-09 | already present (adapted) | `failure_summary()` plus the preflight report name the missing input and the backend state instead of implying success | `distributed_worker.py`; `preflight.py` |
| [#193](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/193) | feat(roihu): step diagnostics, settings reporting and runbook (#188) | 2026-10-02 | already present (adapted) | `preflight_report()` (credential-free settings + backend probes) and `docs/AI26_LASKIN_OPERATIONS.md` | `preflight.py`; `tests/test_analysis_runtime.py` |
| [#224](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/224) | Diagnose Step 1 empty Mongo eligibility with per-status counts | 2026-10-09 | already present | `failure_classes` and `failure_summary()` per cycle | `distributed_worker.py` `_run_bounded_cycle`; `tests/test_issue_330_worker_cycle_telemetry.py` |
| [#289](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/289) | Green the default branch: repair four landed defects, fix Step 7 output, add its missing ... | 2026-10-14 | not applicable as a port | the defects are EP24 files; the class (a test asserting the old behaviour) is handled on this repository as #369 | read: PR body and diff |

### G. Orchestration and ordering

| Upstream PR | Title | Merged | Verdict | Destination in DA | Evidence |
| --- | --- | --- | --- | --- | --- |
| [#291](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/291) | Add strict per-country sequential pipeline and diagnose failed Step 1 rows | 2026-10-14 | already present (adapted) | one flock-protected wrapper, bounded claims, per-cycle outcome counts, dead-letter | `scripts/run_ai26_laskin.sh`; `distributed_worker.py` |
| [#286](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/286) | Fix Step 9 empty-upstream false success, CPU Allas setup and EP24 log paths | 2026-10-14 | already present (adapted) | "nothing to do" is a distinct `idle` outcome; work seeded without progress exits non-zero with a warning; a runtime/manifest mismatch is reported by the drift check | `_cycle_exit_code`; `tests/test_issue_101_worker_cycle_status.py` |
| [#173](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/173) | Fix Step 4 summary pipeline integration, memory/RAG, Mongo and Redis | 2026-10-02 | already present (adapted) | one worker composes record resolution, memory/RAG context, Mongo results and Redis coordination; each backend is probed before the cycle | `distributed_worker.py` `build_worker`; `preflight.py` |
| [#282](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/282) | fix(step8): do not mark failed SNA rows complete | 2026-10-13 | already present | a failed analysis is written as a terminal failure and dead-lettered; it is never a completed row | `AI26TaskWorker.run_once`; `tests/test_issue_300_terminal_truncation.py` |
| [#226](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/226) | Fail Step 1 explicitly when Mongo input is empty | 2026-10-09 | already present (different semantics) | an empty ready queue is idle, not success-by-accident: seeded-without-progress and retry-only cycles exit 1 | `distributed_worker.py` `_cycle_exit_code` |
| [#228](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/228) | Stop Step 2 falsely completing 100 failed frame analyses | 2026-10-09 | already present | terminal failure + dead-letter instead of a completed row; media-less stages record `not_applicable` | `tests/test_issue341_media_applicability.py` |
| [#229](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/229) | Repair Step 1 false-complete records and block invalid Step 2 input | 2026-10-09 | already present | `validate_task` quarantines a stale task envelope before any model call | `tests/test_distributed_worker.py` |
| [#288](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/288) | Submit complete EP24 country pipeline with one ordered SLURM command | 2026-10-14 | not applicable | single ordered SLURM command for a country pipeline | read: `scripts/roihu/run_country_pipeline.sh` — Laskin has no SLURM |
| [#201](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/201) | Fix Roihu sbatch helper path under Slurm spool execution | 2026-10-02 | not applicable | SLURM spool path resolution | read: PR body |
| [#190](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/190) | Build Roihu steps 1-6 integration harness (#188) | 2026-10-02 | not applicable | Roihu steps 1-6 integration harness | read: PR body |
| [#191](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/191) | Prepare CSC Roihu steps 1–6 test harness (#188) | 2026-10-02 | not applicable | Roihu test harness | read: PR body |

### H. Reproducible quality review

| Upstream PR | Title | Merged | Verdict | Destination in DA | Evidence |
| --- | --- | --- | --- | --- | --- |
| [#295](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/295) | docs(#241): reproducible 30-source FI/PL/PT quality review template | 2026-10-15 | **ported** | `docs/AI26_QUALITY_REVIEW_TEMPLATE.md`, re-derived for AI26 arenas, signifiers and imaginaries | shipped in a8e6eb8; this PR keeps it |

### Named in the issue but never merged upstream

| Upstream PR | Title | State | Verdict | Destination in DA | Evidence |
| --- | --- | --- | --- | --- | --- |
| [#296](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/296) | fix(#238): Step 8 honours the shared evidence-budget variable | **closed, not merged** | not applicable | no per-stage character variable exists in DA to shadow a shared one; context budgets come from named profiles | `context_profiles.py` `max_context_chars`; `production_context.py:48` |

---

## 167 PRs dispositioned as clusters

These are dispositioned by class with the criterion stated, not guessed one by one: they touch
files that do not exist in DA and cannot be ported without replacing AI26's locked methodology.
Every number in the second column is a merged PR of that repository and resolves at
`https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/<number>`; they are listed
bare to keep the table readable.

| Cluster | PRs | Verdict | Why | Count |
| --- | --- | --- | --- | --- |
| EP24 country codebook and bilingual-label audits | 73, 75, 76, 77, 78, 79, 80, 81, 83, 84, 85, 86, 87, 88, 89, 93, 94, 96, 97, 98, 99, 100, 104, 105, 106, 107, 108, 109, 110, 112, 113, 114, 115, 118, 119, 120, 123, 125, 126 | not applicable | Per-country EP24 election codebooks (FI/PL/PT/HR/SE/FR/DE/BG/ES/HU), bilingual label coverage, homoglyph and identity-fold audits. AI26's codebooks are a locked contract (`schemas/research-record.schema.json`, `config/projects/ai26.yaml`) and none of these files exist here. | 39 |
| EP24 entity resolution and electoral-list relations | 82, 145, 146, 147, 148, 150, 151, 153 | not applicable | Entity registry, surname/organisation disambiguation, short-alias scoping, electoral-list relations. AI26 has no entity registry; its actor identity is carried by the canonical record and codebook. | 8 |
| EP24 DNA / SNA / RDF stage implementations | 164, 181, 183, 187, 189, 195, 199, 200, 243 | not applicable | Leifeld-compatible DNA, Castells SNA, CSV-RDF projection and the EP24 stage contract. DA has its own Phase 2 modules (`discourse_network/`, `sna/`, `rdf.py`) and Phase 2 is opt-in and experimental. | 9 |
| Roihu SLURM job scripts, Allas/rclone and module loading | 192, 202, 210, 211, 213, 218, 219, 220, 223, 250, 253, 254, 277 | not applicable | sbatch profiles, `module load`, Allas/S3 utilities, per-step environments, job log routing. Laskin runs staggered cron under a flock; there is no scheduler and no Allas. | 13 |
| vLLM video inference, ASR/OCR backends and frame extraction | 20, 23, 25, 27, 28, 29, 30, 31, 34, 36, 37, 38, 39, 42, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 58, 59, 61, 62, 63, 65, 66, 69, 70, 71, 130, 131, 133, 134, 135, 136, 138, 139, 141, 143, 159, 174, 227, 231, 234, 235, 245, 248, 249, 264, 265, 266, 273 | not applicable | Qwen3-VL, Whisper/torchaudio, EasyOCR, keyframe sampling, video scroll sentinels. AI26 processes text-first social-media records; its optional media path consumes already-materialised frames. | 59 |
| EP24 Roihu pilot preparation and run gating | 263, 268, 269, 270, 271, 272, 275, 276, 278, 279, 281, 283, 284 | not applicable | Per-step pilot launchers, evidence-coverage worklists and quality gates for the EP24 corpus. | 13 |
| Documentation, CI plumbing and dependency bumps | 1, 3, 6, 7, 8, 9, 10, 13, 14, 15, 16, 17, 18, 21, 26, 40, 41, 43, 44, 155, 171, 175, 177, 203, 207, 260 | not applicable | Initial project layout, vLLM/transformers bumps, README/CI fixes, Python standards. | 26 |

---

## What this PR changes, and what it deliberately does not

Additive only. No prompt file, codebook, schema, stage contract or Phase 1 decision changed.

1. **`prompt_budget.py` (new)** — the shared budget contract: reserves for the answer and the JSON
   shape, per-section caps, in-band truncation, per-section accounting.
2. **`context_envelope.py`** — the eight-section envelope renders through that contract. Every
   header is still emitted and the section order is unchanged; only how much of each layer fits is
   bounded. `LACLAUGPT_PROMPT_BUDGET_CHARS=0` restores the previous unbounded rendering.
3. **`stages/shared.py` + the three model stages** — the model-visible size is logged *before* the
   call and stored as `prompt_budget`; model-run metadata gains the effective generation settings,
   their fingerprint, the attempt count and the prompt size.
4. **`llm/ollama.py`, `llm/multimodal.py`, `llm/structured_output.py`** — a blank HTTP-200 answer is
   retried a bounded number of times and then raises `LLMEmptyResponseError`, instead of being
   stored or cached as an analysis.
5. **`task_queue.py`, `distributed_worker.py`** — durable results are bound to a fingerprint of the
   effective generation settings; a mismatch logs `resume_invalidated` and re-analyses.
6. **`distributed_worker.enforce_local_model`** — a missing provider dependency now fails before the
   first claim instead of after it.

Not changed, on purpose: the eight-section prompt contract, the stage registry, the research-record
schema, the codebooks, `config/projects/ai26.yaml`, the Phase 1/2 split, and every research decision
in `stages/`. The budget bounds how much of the *same* instrument reaches the model; it does not
change what the instrument is.

## Verification (run on this branch)

```
PYTHONPATH=src .venv/bin/python -m pytest -q -o addopts=''
1147 passed, 1 skipped, 464 warnings in 18.78s

PYTHONPATH=src .venv/bin/python tools/verify_contracts.py
all Analysis contract checks passed

.venv/bin/python -m ruff check <touched files>
All checks passed!
```

The four new regression files are `tests/test_issue_372_empty_response_retry.py` (7),
`tests/test_issue_372_prompt_budget.py` (12), `tests/test_issue_372_resume_fingerprint.py` (13) and
`tests/test_issue_372_worker_preflight.py` (3).

**Sabotage proof for the budget invariant.** `available = budget - reserve_output - reserve_schema`
was replaced with `available = budget` in `prompt_budget.allocate`:

```
FAILED tests/test_issue_372_prompt_budget.py::test_rendered_text_never_exceeds_the_model_visible_budget
1 failed, 11 passed
```

The file was then restored from a byte copy and checked:
`21500af3e48753cb855ee5ae0f0875cd33f281741b184c4945747ab2af0348a5  prompt_budget.py: OK`,
and the same 12 tests passed again.

## Superseded

`docs/AI26_UPSTREAM_PORT_AUDIT.md` (commit `a8e6eb8`) is removed by this PR: its central conclusion
about #287 is corrected above, and its two adopted artefacts — the quality-review template and the
evidence tests — are kept. Nothing else from it was relied on.
