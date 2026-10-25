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


## The 2026-10-23 upstream delta (issue #382), re-evaluated

#372 screened upstream through ~#296. Upstream then merged nine numbered PRs and one unnumbered
Step-4 fix. They are re-evaluated here against AI26 `main` at `c3eccee` (the revision deployed on
Laskin at the time of this review), **not** against the audit's own conclusions.

| Upstream | Failure class | AI26 path it would hit | Disposition | Evidence |
| --- | --- | --- | --- | --- |
| **#305** | A malformed regex (`\\d` vs `\d`) made ID recovery never match, so recovery silently did nothing | identity/ID parsing helpers | **Class live, no analogous parser** — AI26 records are keyed by canonical `source_url`/`record_id`, not by a reconstructable structured media ID; there is no ID-reconstruction regex to mis-escape. The general lesson (a recovery path that silently never matches) is covered by #382's requirement that each fix carry a failing-then-passing regression test. | `canonical.py` (identity fields); no `_HEPP24_ID`-style parser exists |
| **#304** | Unidentifiable rows blocked a whole batch; quarantine must be audited, and an all-invalid batch is not a failure | handoff validation, per-record isolation | **Already present, different mechanism** — a record that cannot be claimed or validated is quarantined with a reason and counted, and the cycle continues; `quarantined` is a cycle-level count, not a crash. | `distributed_worker.py:580-609` (`last_quarantined`, quarantine on stale revision); `tests/test_issue_101_worker_cycle_status.py` |
| **#303** | Missing source identity recovered conservatively from validated composite identity, never invented | record identity | **Already present** — a record without a usable canonical identity is quarantined rather than reconstructed from a guessed key; nothing in AI26 invents an identity for a record it cannot identify. | `canonical.py`; `distributed_worker.py:599` |
| **#302** | "No eligible rows" after a completed eligible subset was reported as an alarm; completed-subset and empty-upstream must be distinguishable | cycle outcome reporting | **Already present** — `idle` is a distinct outcome from `completed`, and the cycle summary separates claims, completions, retries and dead-letters. | `distributed_worker.py:800-810` (`_cycle_verdict`); `tests/test_ai26_cycle_outcome.py` |
| **#301** | Refreshed codebook context mutated cumulative upstream columns and broke the checkpoint | context building, checkpointing | **Not applicable as a mechanism** — AI26 persists one result document per record (unique `(project_id, run_id, idempotency_key)`); there is no cumulative CSV checkpoint whose upstream columns could be mutated. Context is built per record and travels in the request/provenance, not as a mutable upstream column. | `distributed_worker.py` durable store; `tests/test_issue_330_worker_cycle_telemetry.py` |
| **#300** | Per-row exception diagnostics discarded; stale derived cache accepted | failure diagnostics, staging cache | **Diagnostics already present; the stale-cache half was a real gap and is now fixed** — see below. | `last_failure_class`; `failure_summary()`; `tests/test_staging.py` (new cache-trust tests) |
| **#299** | One bad media object aborted a whole batch instead of failing per row | staging | **Already present** — staging classifies per object (`missing`/`corrupt`/`failed`) and a record survives a permanently missing object; the batch does not abort. | `staging.py` (`StagedObject.status`); `tests/test_staging.py::test_missing_object_is_permanent_not_retriable`, `::test_stage_record_is_ok_when_a_referenced_object_is_permanently_missing` |
| **#298** | A value normalised differently on the two sides of a round trip was read as a mutation, producing a false failure | prompt digest and contract reporting | **Class live and fixed twice, in two places where the same value crossed a representation boundary** — see below. | `ai26.py::_prompt_record`; `tools/check_ai26_contracts.py`; `tests/test_issue_382_prompt_digest.py`; `tests/test_issue_382_contract_check.py` |
| **#297** | A nonempty but truncated cached artefact was reused forever because existence was the only test | **media staging cache** | **Real gap in AI26, now fixed** — see below. | `staging.py::stage`; six new tests in `tests/test_staging.py` |
| **`812aedf`** (unnumbered, Step 4) | A truncated model response could be cached as a completed summary | structured generation | **Already present, stronger** — a truncated completion is detected from `finish_reason`, recorded, and terminal truncation failures are automatically re-armed rather than left as completed rows. | `llm/ollama.py:344-346`; `distributed_worker.py:552-557, 621, 694` |


### Two more ports in the same class, found while auditing

**A published digest that could not verify the text beside it (`ai26.py`).** `render-prompt --json`
hashed the prompt file's on-disk **bytes** while `--show` published the **text**. On an LF checkout
those are the same bytes; on a checkout whose line endings were converted they are not, so
`sha256(text)` did not equal the reported digest and two tests in `tests/test_issue_341_ai26_cli.py`
encoded the contradiction — invisible in Linux CI, fatal on Windows. The digest now covers the
published text, which is identical to the old value on LF checkouts (so no published hash moves) and
verifiable everywhere. `tests/test_issue_382_prompt_digest.py` pins the contract on both line-ending
flavours.

**A contract check that died instead of naming the disagreement (`tools/check_ai26_contracts.py`).**
On the live Laskin deployment it exits **2** with `Contract check cannot read/parse schema: 'const'`:
it read `properties.schema_version.const`, but Data Visualization declares an **enum**
(`["1.1.0", "1.2.0"]` — deliberately, since Analysis emits 1.2.0 while Collection still declares
1.1.0). The tool named neither the repository nor the disagreement, so the documented contract
validation was, in practice, unusable on the machine it was written for.

It now reads a schema's **accepted version set** (`const` or `enum`), compares the version Data
Analysis actually emits against every sibling, keeps the required-field comparison, and reports each
repository's versions, how they were declared, and the exact field difference (`missing=[…]
extra=[…]`). Exit 1 is a disagreement and names the repository; exit 2 is an unreadable schema and
names the file. Eight tests in `tests/test_issue_382_contract_check.py` build throwaway sibling
repositories to pin all four behaviours.

Measured against the live deployment (2026-10-25, all three checkouts current, before this change
was deployed):

```
$ python tools/check_ai26_contracts.py --collection …/LaclauGPT-Data-Collection \
                                       --visualization …/LaclauGPT-Data-Visualization
Contract check cannot read/parse schema: 'const'          # exit 2, names nothing
```

With this change the same command on the same schemas reports:

```
analysis:      schema_version ['1.2.0'] (declared by const)
collection:    schema_version ['1.1.0'] (declared by const)
visualization: schema_version ['1.1.0', '1.2.0'] (declared by enum)
emitted by Data Analysis: 1.2.0
FAIL: LaclauGPT-Data-Collection accepts ['1.1.0'] but Data Analysis emits 1.2.0 …
```

That `FAIL` is a **finding, not a bug in this repository**: Data Collection's schema still declares
1.1.0 and must be brought forward in its own repository. Raising it here is the point — the
previous behaviour hid it behind a `KeyError`.

## Laskin deployment check (2026-10-25, before this change)

Read-only, on the machine the cron actually runs:

```
$ git -C /mnt/workspace/LaclauGPT-Data-Analysis log -1 --format=%H
c3eccee9a7274e54f63fed03e8e462a51ccadd34        # == origin/main at review time
$ .venv/bin/python -c "import sys, laclaugpt_data_analysis as m; print(sys.version.split()[0], m.__file__)"
3.11.14 /mnt/workspace/LaclauGPT-Data-Analysis/src/laclaugpt_data_analysis/__init__.py

$ python -m laclaugpt_data_analysis.preflight            # status: ok, model gemma4:e4b, llm 127.0.0.1:11434
$ python -m laclaugpt_data_analysis.deploy_drift --json  # all three checkouts: behind 0, ahead 0, needs_attention []
```

No cycle was started and no checkout was modified by this review; the bounded end-to-end run is
reported on the issue rather than claimed here.

### The cache-trust port: a cache entry is reused only while it can still be believed

`MediaStager.stage()` reused any existing cache file when the record carried no checksum. Two
consequences, both the #297/#300 class:

* a **zero-byte** entry — an interrupted write, a cleanup, a restore — was returned as
  `status="cached"`, so the failure surfaced later in whichever reader opened the file;
* a **replaced or truncated** object was reused indefinitely, because the store's reported size was
  only consulted on the download path and never on the cache-hit path.

Now: a cache entry is reused when its checksum matches, or (with no checksum) when its size agrees
with what the store reports. A zero-byte entry is always refetched. When the store cannot answer —
no `stat_ref`, a transport error, or an object that has since disappeared remotely — the local copy
is **kept**, because a network outage must not discard media that was staged successfully.
`StagingPolicy.verify_cached_size` exposes the trade-off (one metadata call per cache hit) and can
be turned off. `StagingReport.invalidated` / `provenance()["staging_invalidated_cache_hits"]` makes a
cache that keeps going bad visible instead of looking like ordinary first-time downloads.

Six tests in `tests/test_staging.py` pin the behaviour: empty entry refetched, stale size
refetched, outage keeps the local copy, remotely deleted object keeps the local copy, the opt-out,
and the aggregate count. No prompt, codebook, taxonomy or schema was touched.

## Done-when checklist for #372

- [x] Inventory with source links and dispositions (this document).
- [x] Selected changes merged with regression coverage (this PR; suite green on a clean worktree).
- [x] Locked AI26 Phase 1 behaviour intact — no prompt, codebook or schema touched.
- [x] Running Laskin pipeline verified against the deployed revision (see the issue comment for the
      measured cycle and the deployed SHA).
