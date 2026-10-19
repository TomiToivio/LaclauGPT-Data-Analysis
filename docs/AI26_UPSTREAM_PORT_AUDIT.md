# Upstream port audit: Multimodal-Analysis → AI26 Data-Analysis (issue #372)

**What this is.** A disposition for every upstream improvement this issue asks about, plus a screening
of the wider merged history, verified against the AI26 code **as it runs on Laskin** rather than against
its README. Nothing here ports EP24 behaviour: the upstream repository analyses EP24 video with Roihu
SLURM jobs; this repository analyses AI26 social-media records on a Laskin cron. What travels is the
*failure class*, not the code.

**Method.** All twelve PRs named in #372 were read in full (body, changed files, intent). The remaining
merged history — **200 PRs** — was screened by title and file set for classes that could exist here;
anything EP24-step-specific or SLURM/Roihu-specific was dispositioned without a port. Each "already
present" row below cites the AI26 file or test that carries the behaviour, so the claim can be checked
rather than believed.

## The twelve named PRs

| Upstream | What it fixed | AI26 disposition | Evidence |
| --- | --- | --- | --- |
| **#296** | A stage-passed explicit value shadowed the shared evidence-budget variable, so the documented override silently did nothing | **Already present, different mechanism** — no per-stage char variable exists to shadow. Budgets come from named `ContextProfile`s selected by one environment variable. | `context_profiles.py` (`max_context_chars` per profile); `production_context.py:48` reads `LACLAUGPT_CONTEXT_PROFILE`; `tests/test_layered_runtime.py:62` asserts the resolved value |
| **#295** | Reproducible manual quality-review template | **Ported** → `docs/AI26_QUALITY_REVIEW_TEMPLATE.md`, re-derived for AI26's arenas, signifiers and imaginaries rather than FI/PL/PT country batches | this PR |
| **#294** | Shared prompt/context builder contracts | **Already present, and stronger** — the stage registry is machine-readable and an offline validator fails when registry and prompt references drift, before any model call | `stages/registry.json`; `ai26.py validate-contract`; `tests/test_issue_341_validate_contract.py` |
| **#293 / #292** | Dependency preflight for missing `pymongo` / `redis` imports | **Already present, adapted** — `--check` probes the LLM endpoint, model presence and Redis reachability and fails closed *before* claiming work. Import-level checks are redundant because the worker is launched through the same venv. | `scripts/run_ai26_laskin.sh --check`; `docs/AI26_LASKIN_OPERATIONS.md` |
| **#291** | Ordered per-country execution and diagnosis of failed steps | **Already present** — one wrapper, one flock, bounded claims, per-cycle outcome counts, `failure_classes`, dead-letter | `distributed_worker.py` (`run_once`, `bounded_cycle`); `tests/test_issue_101_worker_cycle_status.py`; `tests/test_issue_330_worker_cycle_telemetry.py` |
| **#290** | Evidence provenance clarity; log dropped packet fields instead of losing them silently | **Already present** — evidence is attached with character offsets and an `exact` flag, and a non-verbatim quote is recorded as inexact rather than dropped | `stages/evidence.py` (`locate_quote`, `evidence_ids`); `tests/test_evidence_source_grounding.py` (added here) |
| **#289** | Repaired four landed defects whose tests disagreed with their code (regex double-escaping, grounded-span parser, stale expectations) | **Not applicable as a port** — the defects are in EP24 files. The *class* is live here: the same "test asserts the old behaviour" failure appeared on this repository's `main` today and was fixed as #369. | — |
| **#288** | One ordered SLURM command for the country pipeline | **Not applicable** — Laskin runs staggered cron stages under a flock; there is no SLURM. | — |
| **#287** | Resume hashes did not cover effective generation settings, so changed options could reuse a stale completed analysis | **Design difference, documented rather than ported** — see below | `distributed_worker.py:250` |
| **#286** | Empty-upstream false success; log paths | **Already present in adapted form** — "no work" is a distinct `idle` outcome, not a completion, and a runtime/manifest mismatch is reported by the drift check before the cycle | `distributed_worker.py:554`; `deploy_drift`; `tests/test_issue_353_deploy_drift.py` |
| **#285** | Source grounding: quotations only from original ASR/OCR fields; enforce the budget even for the no-evidence notice | **Already present, and stronger** — AI26 locates each quotation in the original source text and records offsets, so a derived or paraphrased string cannot become evidence at all | `stages/evidence.py`; `tests/test_evidence_source_grounding.py` (added here — the function was previously untested) |

### #287 in detail: why the same fix does not apply

Upstream resumes by hash, so a hash that omits `temperature`/`num_ctx`/`num_predict` silently reuses a
result produced under different settings. AI26 does not resume by configuration hash: the durable
identity is the **immutable handoff key** (`distributed_worker.py:250`), i.e. the source record and its
revision. A changed generation option therefore *cannot* silently reuse a stale analysis in the way #287
describes — but the flip side is real and worth stating: a merged analysis improvement also does not
retroactively re-analyse records that already have a result. Re-analysis is an explicit operator action
(`rearm`), not an automatic consequence of changing settings.

That is a trade-off, not an oversight: automatic re-analysis on every option change would reprocess the
whole corpus each time a prompt is tuned. Changing it would be a methodology decision for the author,
not a port, and is left open deliberately.

## Screened beyond the named twelve

The wider history is overwhelmingly EP24-step-specific (ASR, OCR, frame extraction, Qwen3-VL, Allas,
Roihu). The classes that could generalise, and their AI26 answer:

- **False completion of failed work** (#228 "falsely completing 100 failed frame analyses", #229 "#230
  false-complete records"): AI26 writes an explicit `not_applicable` status instead of a silent success,
  and the behaviour is pinned by `tests/test_issue341_media_applicability.py`.
- **Silent reuse of an empty cache** (#247): AI26's evidence gate records what it found and marks
  inexact quotes, so an empty result cannot pass as a verified one.
- **Prompt-budget overrun** (#246, #230): budgets are profile values, applied before the call, and the
  resolved profile is asserted (`tests/test_layered_runtime.py`).
- **Log paths and predictable artefacts** (#222, #286): AI26 logs through one stable per-stage path
  documented in `docs/AI26_LASKIN_OPERATIONS.md`; the drift check reports a stale runtime in that same
  log.
- **Archive-and-restart / reset tooling** (#252, #253): not applicable — AI26's recovery path is
  re-running a bounded cycle, with no archive step to get wrong.

## What this PR actually changes

1. **`docs/AI26_QUALITY_REVIEW_TEMPLATE.md`** — the one artefact worth copying wholesale (#295),
   adapted so a reviewer samples AI26 arenas and can actually check the properties AI26 claims.
2. **`tests/test_evidence_source_grounding.py`** — ten contracts for `locate_quote` and `evidence_ids`.
   The evidence gate decides whether a model's sentence becomes citable evidence, and it had **no
   tests**; that is the #285 class in its AI26 form, so the port is coverage rather than new behaviour.

No pipeline semantics, codebook, prompt or schema was altered. No upstream code was copied.

## Done-when checklist for #372

- [x] Inventory with source links and dispositions (this document).
- [x] Selected changes merged with regression coverage (this PR; suite green on a clean worktree).
- [x] Locked AI26 Phase 1 behaviour intact — no prompt, codebook or schema touched.
- [x] Running Laskin pipeline verified against the deployed revision (see the issue comment for the
      measured cycle and the deployed SHA).
