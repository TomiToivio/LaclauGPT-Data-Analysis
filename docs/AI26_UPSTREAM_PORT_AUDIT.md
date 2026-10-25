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
| **#304** | Unidentifiable rows blocked a whole batch; quarantine must be audited, and an all-invalid batch is not a failure | handoff validation, per-record isolation | **Ported in the second pass — see the matrix below** (#384): a handoff that cannot become a task is skipped, named, counted and left ready upstream instead of raising out of the seeding pass. My first reading, "already present", described the *claim-time* quarantine and missed the seeding pass. | `distributed_worker.seed_ready_tasks`; `tests/test_issue_382_seed_quarantine.py` |
| **#303** | Missing source identity recovered conservatively from validated composite identity, never invented | record identity | **Already present** — a record without a usable canonical identity is quarantined rather than reconstructed from a guessed key; nothing in AI26 invents an identity for a record it cannot identify. | `canonical.py`; `distributed_worker.py:599` |
| **#302** | "No eligible rows" after a completed eligible subset was reported as an alarm; completed-subset and empty-upstream must be distinguishable | cycle outcome reporting | **Ported in the second pass — see the matrix below** (#386): my first reading, "already present", was wrong. `idle` *is* distinct from `completed`, but the seeding pass said "nothing new" in the same words for an empty source, a malformed handoff and a completed subset; `seed_disposition` now names the zero. | `distributed_worker.seed_ready_tasks` / `seed_disposition`; `tests/test_issue_382_seed_disposition.py` |
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

### Two rows above were wrong on their first reading

The #304 and #302 rows in the delta table said "already present". Re-reading them against the
seeding pass — not the claim path — showed the opposite, and two sibling changes on this issue
(#384, #386) ported them properly. The rows above point at those, rather than keeping a disposition
that the code contradicts.

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

## Delta since #372: the upstream changes reviewed for #382 (2026-10-25)

The audit above was closed against upstream `main` at the time of #372. This section reconciles it
with upstream `c3ffc569dea1b2c008000075f23bbea46ef8dfc8`, which contains nine merged PRs and one
unnumbered commit **newer** than that review. Each row was read against the current AI26 code, not
against the earlier disposition, because a disposition can age.

| Upstream | Failure class | AI26 path | Disposition | Evidence |
| --- | --- | --- | --- | --- |
| [#305](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/305) | A double-escaped character class in an identity regex never matched, so recovery silently returned nothing | any AI26 identifier parsing | **Not applicable, and checked** — HEPP24's `YYYYMMDD` id convention does not exist here, and no regex in `src/` carries a doubled escape | `grep -rn 'r"[^"]*\\\\[dws]' src/` → no matches (2026-10-25) |
| [#304](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/304) | One unidentifiable row aborted a whole batch; rows that could not be identified were neither quarantined nor audited | `distributed_worker.seed_ready_tasks` | **Ported** — a handoff that cannot become a task is skipped, named, counted and left ready upstream instead of raising out of the seeding pass | `tests/test_issue_382_seed_quarantine.py` (10 tests) |
| [#303](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/303) | Missing source identity could not be recovered, and inventing one was worse than failing | `WorkerBinding.task_from_handoff` | **Deliberately not ported** — AI26's identity is the Collection handoff key and its `source_url`; there is no composite `_storage_id` to reconstruct from, and AI26 must not synthesise an identity it was not given | `task_from_handoff` (identity comes from the handoff only); `TaskEnvelope.validate` refuses an empty `record_ref` |
| [#302](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/302) | A completed-and-eligible subset was reported with the same message as an empty or misconfigured source | `distributed_worker.seed_ready_tasks`, cycle log | **Ported, second pass** — the first reading of this row said "already present" and it was wrong; see below. `seed_ready_tasks` now fills a count mapping and `seed_disposition` names the zero: `seeded` / `upstream_empty` / `all_rejected` / `budget_zero` / `no_new_work` | `tests/test_issue_382_seed_disposition.py` (8 tests) |
| [#301](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/301) | A mutated context was written into the cumulative frame and rejected at checkpoint, losing completed calls | task envelope ↔ frozen manifest | **Already present, and stronger** — a task carries `config_revision` and `codebook_revision` and is refused when either differs from the frozen manifest, before the claim | `WorkerBinding.validate_task` (five-way manifest comparison) |
| [#300](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/300) | Per-row exception detail was discarded; a stale derived cache was reused; the failure report was not durable | `DurableTaskStore.write_failure` | **Already present in adapted form** — the failure journal stores the error string plus a `diagnostics` mapping per idempotency key, and terminal failures are a separate state that is not silently retried | `write_failure(..., diagnostics=...)`; `has_terminal_failure`; `tests/test_issue_300_terminal_truncation.py` |
| [#299](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/299) | A staging batch aborted on a row with a missing media filename | `staging.stage` | **Already present** — staging verifies size and, where the record supplies one, SHA-256, and returns a per-object result rather than raising out of the batch | `staging.py` (cache-hit verification, per-object `StagedObject`) |
| [#298](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/298) | An unset nullable status crashed a normalisation step | stage results | **Not applicable** — AI26's status vocabularies are closed `Literal`s that carry an explicit `not_applicable` member rather than a nullable field | `critical_ai.FindingStatus`, `dna_statement_coding.AgreementStatus` |
| [#297](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/297) | A non-empty but truncated cached clip was reused forever | `staging.py` cache | **Already present, and stronger** — a cache hit is validated by size and checksum, so a truncated artefact is rebuilt rather than reused | `staging.py` module docstring and `stage()` |
| `812aedf` (unnumbered) | A truncated model response was cached and reused | model calls | **Not applicable** — AI26 keeps no LLM response cache; a retry re-asks the model, and truncation is a terminal failure with its own re-arm path | `grep -rln "reply_cache\|llm_cache\|response_cache" src/` → no matches |

### The one defect this port fixed

`seed_ready_tasks` converted each ready handoff with no error boundary. One handoff missing its
`source_url` — or carrying a `run_id` that did not match the frozen manifest — raised out of the
**entire** seeding pass. The consequences compounded:

1. every record after the bad one in that page was never queued that cycle;
2. the bad row stayed `ready` in the collection, so the next tick read it first and failed again;
3. the cycle then reported `idle` with zero work, which reads like a drained corpus rather than a
   refusal.

That is a permanent stall that looks like success — acceptance criterion 4's "stuck retry loops /
false-complete" in its AI26 form, and the same class as upstream #299/#303/#304 seen from three
angles. The fix keeps the return contract (tasks published) and adds an optional accumulator, so
existing callers and their six assertions are untouched.

### #302, second pass: what the first reading missed

The quarantine above stops a *refused* row from being silent. It does not stop a **zero from
being silent**, and the first pass through this table read the existing code as if it did.

The reasoning there was that "no work left" is the `idle` outcome and the alarming warning is
gated on `seeded > 0`. Both statements are true, and together they say the opposite of what was
concluded: the alarm is *suppressed exactly when nothing was handed over*. A cycle where Collection
returns nothing and a cycle where every record is already analysed produce the same `idle` outcome,
the same empty `failure_classes`, the same `seeded == 0`, and exit status 0.

That matters because the mismatch this pipeline can suffer is not "too much work". It is a frozen
run manifest whose `run_id`, `project_id` or Phase 1 `date_after` no longer matches what Collection
is publishing. When that happens nothing arrives, every hourly tick is idle, and the log reads like
a finished corpus forever. "Drained queue" is not evidence of "drained corpus".

So `seed_ready_tasks` reports the counts behind its zero, and `seed_disposition` names it:

| disposition | means | level |
| --- | --- | --- |
| `seeded` | work was published | INFO |
| `no_new_work` | rows arrived, all already analysed at this generation | INFO |
| `all_rejected` | rows arrived, every one refused by the quarantine | INFO, with the quarantine log |
| `budget_zero` | `--max-tasks 0`, so no work was attempted | INFO |
| `upstream_empty` | **Collection handed over nothing** | WARNING, naming the run id |

The empty case is the one that earns a warning, because it is the only one where an idle cycle is
being read as evidence about the corpus. The rest are ordinary and stay at INFO so the hourly log
stays readable.
