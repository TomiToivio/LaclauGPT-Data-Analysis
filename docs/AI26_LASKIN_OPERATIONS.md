# AI26 Laskin operations: drift, failure classes and recovery

**What this document is.** The runbook for the *failure modes* discovered while operating the
AI26 pipeline on Laskin. It is the companion to [AI26_LASKIN_ANALYSIS.md](AI26_LASKIN_ANALYSIS.md),
which is the operator guide: install, Ollama, freeze, preflight, run once, cron, staging,
provenance, privacy. **Read that first; read this when something is wrong or when a result
looks inconsistent with `main`.**

It deliberately does not repeat procedures that already live there. What it adds is the
operating knowledge that only exists because things went wrong:

1. the deployed checkouts drift from `main`, and nothing pulls them (issue #353);
2. the environment can lag the repository even when the checkout is current;
3. the log's failure lines are not all faults, and the ones that are can be told apart;
4. what an operator or agent must *ask* before doing.

## 1. The runtime is the checkout

The three cron lines run their checkouts directly, and the Analysis venv is an **editable**
install pointing at the checkout's `src/`. There is no build step and no copy: **whatever the
checkout contains is what runs**, which cuts both ways.

Measured on 2026-10-15: Analysis was nine commits behind and three merged fixes were silently
not in effect, so every measurement taken from the live log that day described *pre-fix*
behaviour. One cause had been filed as four separate bugs.

### Check it

```bash
python -m laclaugpt_data_analysis.deploy_drift                 # this checkout + its siblings
python -m laclaugpt_data_analysis.deploy_drift --json           # machine-readable
python -m laclaugpt_data_analysis.deploy_drift --threshold 5    # tolerate five commits of lag
```

`run_ai26_laskin.sh` calls this itself, right after the configuration preflight, in both
`--check` and normal runs: silent when everything is current, one `WARNING` per lagging
checkout otherwise. The wrapper never refuses to run because of drift — a stale runtime is a
risk, not an emergency, and refusing would stall the corpus.

Reading the output: `behind` and `ahead` are commit counts against `origin/main`; `diverged`
means both are non-zero and the checkout needs a human decision, not a fast-forward; `unknown`
means git, the network or the path failed, and the reason is in `detail`.

### Refresh, deliberately

Refreshing makes every other fix effective, so it is worth doing on purpose rather than as
housekeeping:

| Checkout | Suggested handling |
|---|---|
| `LaclauGPT-Data-Visualization` | usually safe: no writer, so fast-forward it |
| `LaclauGPT-Data-Analysis` | fast-forward **between** cycles, then confirm the next tick |
| `LaclauGPT-Data-Collection` | **ask first**: it is a live collector writing a corpus |

After refreshing Analysis, the hourly cycle detects the stale run manifest and re-freezes it
automatically (`AI26 manifest stale; re-freezing before scheduled analysis`, new `git=` and tree
hash). That self-healing step works; you do not need to touch the manifest by hand.

### Working in a worktree, and why it fools you

A git worktree of the repository has **no `.venv`**, and the wrapper fails closed without one:

```
ERROR: virtualenv interpreter not found: <worktree>/.venv/bin/python
```

Two traps follow. First, the wrapper will not run from a bare worktree at all. Second, if you
run a *test* there with the shared venv, the editable install resolves imports to the **shared
checkout's** `src/`, so you may be testing the wrong tree entirely. Set `PYTHONPATH=<worktree>/src`
and confirm `laclaugpt_data_analysis.__file__` points where you think it does before believing a
green run. To exercise the wrapper itself from a worktree, symlink the real venv into it.

## 2. The environment can lag the repository too

The venv is the runtime interpreter (`$ROOT_DIR/.venv/bin/python`), so a dependency added to
`pyproject.toml` is not in effect until the venv is refreshed — exactly the same failure mode as
a stale checkout, one layer down.

Seen on 2026-10-15: a dev extra gained `jsonschema`, the venv did not have it, and the whole test
suite aborted at **collection** rather than failing a test, which reads like a broken repository
instead of a stale environment. If `pytest` reports a collection error naming a module you can
find in `pyproject.toml`, refresh the environment before you go looking for a bug.

## 3. Reading a cycle's log without false alarms

Healthy signals, in order of authority:

* `AI26 Laskin analysis end worker_status=0 report_status=0 status=0` — the authoritative line;
* bounded claims (`claims` 5-12) with `completed` in the same range, and a drained queue showing
  `idle`;
* `AI26 seed disposition=...` — what the zero meant, when the pass published nothing (see below);
* `already running; exiting cleanly` — the flock doing its job when ticks overlap, not an error;
* the periodic report's `generated` and `records_considered` moving by exactly the work the cycle
  completed. If they do not move together, something is wrong with durability, not with the model.

### An `idle` cycle is not proof that the corpus is finished

A cycle that published nothing used to look the same whatever the cause. It now names the zero:

| `disposition=` | means | what to do |
| --- | --- | --- |
| `seeded` | work was published | nothing |
| `no_new_work` | rows arrived, all already analysed at this generation | nothing |
| `all_rejected` | rows arrived, every one refused as an unusable handoff | read the quarantine lines above it |
| `budget_zero` | `--max-tasks 0` | nothing; you asked for no work |
| `upstream_empty` | **Collection handed over nothing for this run** | check the frozen run id, `project_id` and Phase 1 `date_after` against what Collection is publishing |

`upstream_empty` is logged as a **warning** and it is the only one that matters: it is the case
where an idle cycle is being read as evidence *about the corpus* when it is really evidence about
the handoff. The usual cause is a frozen manifest whose run identity or date window has drifted
from Collection's, and the symptom is a pipeline that looks finished forever while nothing is
analysed. Confirm with the ready-handoff count before believing either reading.

Lines that are **not** faults:

* `structured generation truncated (attempt N, finish_reason=length)` — the output ladder widening
  the budget for a long record;
* `taxonomy catch-all: <Model>.<field> value '<x>' is not a member; recorded as 'other'` — the
  model proposed a kind the vocabulary does not carry. The value is preserved in the substitution
  ledger and the record is kept. Count these: a *rising* count for one field is evidence the
  vocabulary should grow, which is the author's decision, not a bug to patch silently;
* `structured parse failed (validation attempt N)` — the one validation-aware retry.

Lines worth acting on:

* `structured JSON decode failed: mode=... pos=... excerpt=...` — the response was not parseable.
  The `mode` names the shape (a prose wrapper, a trailing comma, an unbalanced structure) and the
  excerpt elides every string *value*, so it is safe to paste into an issue. Choose the fix from
  the mode rather than guessing;
* `dead-letter` above zero, or `failure_summary.terminal` increasing — a record has stopped, not
  merely retried. Dead-letters are the ones that need a human;
* any `worker_status` other than 0.

## 4. Bounded work, bounded time, and killing a cycle

`LACLAUGPT_MAX_TASKS` bounds how much *work* a cycle claims; `LACLAUGPT_CYCLE_MAX_SECONDS`
(150 min) bounds how long it may take. The ceiling exists to break a pathological hang, not a
slow-but-healthy cycle: of 495 logged cycles the median is 9 minutes, p90 is 41, and four
historic successes exceeded 70. **Never kill a cycle for looking slow.**

### The reserved backfill slice and a closed stratum (#429 / #433)

Three of the ten slots per cycle (`LACLAUGPT_AI26_BACKFILL_TASKS`, default `3`) are spent
oldest-first on the ready frame instead of on the priority order, so the tail the priority order
cannot reach still drains. The slice is only worth its slots if it reaches the pool it was created
for. The X capture stopped on 2026-10-26 (#401), so the X stratum reaches further back in
publication time than every live stratum: on 2026-11-12 the slice published 29 of its 30 completions
into September-dated X records while the non-X never-analysed pool grew 416 -> 439.

`LACLAUGPT_AI26_BACKFILL_EXCLUDE_PLATFORMS` (comma-separated, **empty by default**) names platforms
the oldest-first backfill walk must skip. The priority walk still sees every platform, so the live
tiers stay exactly as fresh as before; nothing changes until a name is set, and unsetting it restores
the pre-#433 order exactly. This host sets `=x` in `laskin.env` (2026-11-15) because the X stratum is
closed for Phase 1 and can never be refreshed, while the non-X tail can.

Read the effect off the cycle's own disposition line rather than a separate query:
`backfill_excluded_platforms` becomes `1`, `backfill_published` stays `3`, and
`backfill_oldest_published_at` starts advancing through non-X publication dates. If the key is
missing from the line, the deployed worker predates #433 and the switch is inert — check the drift
line before concluding the exclusion does nothing.

If a cycle is genuinely stuck, and a human has decided to terminate it: an unacknowledged Redis
message is reclaimable via `--reclaim-idle-ms`, and MongoDB's unique
`(project_id, run_id, idempotency_key)` index keeps the result idempotent. **Never move the
consumer-group cursor to recover a stuck cycle** — `XGROUP SETID` can move it backwards and
re-process thousands of already handled entries.

## 5. Rollback and uninstall

* **Cron:** the installer is `scripts/install_ai26_laskin_cron.sh`; the analysis entry is one
  tagged line, so removing it is a single edit and nothing else in the crontab is touched.
* **A bad deployment:** revert the checkout to the previous commit — since the checkout *is* the
  runtime, `git revert`/`git reset` is the rollback — then let the next cycle re-freeze the
  manifest. Nothing else caches code.
* **A bad run's results:** results are durable and idempotent, so a re-run from the same handoff
  revision converges rather than duplicating. Prefer re-running a record to editing a stored
  result by hand.
* **The backfill exclusion:** remove or blank `LACLAUGPT_AI26_BACKFILL_EXCLUDE_PLATFORMS` in
  `laskin.env`; the next cycle is back to the pre-#433 oldest-first order. No code change, no
  restart, nothing in the queue to unwind.

## 6. What to ask before doing

Ask, and do not decide alone:

* refreshing or resetting the **Collection** checkout (live collector);
* killing a running cycle;
* any migration, backfill or bulk write over stored records;
* changing a prompt, a codebook, a taxonomy member or a schema — including "just adding" a value
  the model keeps proposing. The catch-all records those precisely so the decision can be made
  with evidence instead of by accident.

Safe without asking: reading anything, running the preflight, running the drift check, running a
bounded cycle, and filing an issue with the evidence.

## 7. Quick reference

```bash
python -m laclaugpt_data_analysis.ai26 status                    # configs, steps, registry
python -m laclaugpt_data_analysis.ai26 stages --json             # the step map from the registry
python -m laclaugpt_data_analysis.ai26 render-prompt --stage discourse --show
python -m laclaugpt_data_analysis.deploy_drift --json            # drift, read-only
python -m laclaugpt_data_analysis.preflight                      # configuration preflight
python -m pytest -q                                              # the suite
```

The step map, its reading order and the maturity status of each step live in
`src/laclaugpt_data_analysis/stages/registry.json` — one machine-readable registry that the CLI
prints and a test pins to the modules, so the map cannot quietly drift from the code.
