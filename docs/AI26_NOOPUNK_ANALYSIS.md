# AI26 analysis on NooPunk

Operator guide for the **user-activated** AI26 analysis batch on **NooPunk**.

This is the counterpart to [`AI26_LASKIN_ANALYSIS.md`](AI26_LASKIN_ANALYSIS.md). The
pipeline is the same and the shared backend is the same; what differs is the policy.
Laskin drains the queue unattended from cron. NooPunk **does not run analysis by
default** — it is an interactive workstation with one consumer GPU, and analysis
starts only when the user starts it.

Part of `TomiToivio/LaclauGPT#71`. Private settings, credentials and research data
never live in this repository; the real machine configuration is in the private
repository.

```text
NooPunk
  user invokes scripts/run_ai26_noopunk_analysis.sh
    └─ bounded AI26 analysis worker (claims N tasks, then exits)
          ├─ reads ready handoffs from remote MongoDB   (same queue as Laskin)
          ├─ stages referenced multimodal objects from CSC Allas / S3
          ├─ runs the AI26 stages on the selected Ollama model
          │     local : gemma4:e2b          (default)
          │     cloud : gemma4:31b-cloud    (explicit opt-in)
          └─ persists results + provenance to MongoDB   (same collections)

Laskin's own hourly cron continues independently. Both nodes write one ai26
namespace; running this batch changes WHO processed an item, never WHAT the
corpus is.
```

Machine identity is execution provenance. It is never part of scientific source
identity, and NooPunk does not create its own database, bucket or codebook.

## Resource policy (the point of this node)

| surface | policy |
| --- | --- |
| browser collection | **always on** — NooPunk's primary duty |
| analysis | **off by default, user activated** |
| visualization | off by default, user activated |

There is deliberately **no cron entry** for analysis on this machine. `config/machines/noopunk.yaml`
sets `capabilities.cron: false` and the execution layer has no NooPunk equivalent of
`config/execution/laskin-cron.yaml`. If you find yourself adding a schedule here,
stop — that would turn an interactive workstation into an always-on analysis node,
which is Laskin's role.

## Canonical lookup order

Before guessing AI26 settings, inspect:

1. `docs/AI26_REFERENCE_CASE.md`
2. `codebooks/public/ai26_v2.yaml` and `codebooks/public/seed_ai_formations.md`
3. `config/projects/ai26.yaml` — study semantics for this run
4. `config/machines/noopunk.yaml` — this machine's capability layer
5. `docs/AI26_DISTRIBUTED_WORKER.md` and `docs/ANALYSIS_RUNTIME.md`
6. private runtime copies under the private root, when authorised

## Layered configuration

The repository composes three independent layers. Keep their responsibilities
separate — do not put study semantics in a machine file or scheduling in a project
file.

| Layer | Public template | Owns |
|---|---|---|
| project | `config/projects/ai26.yaml` | study semantics, codebook/context/prompt selection, stages |
| machine | `config/machines/noopunk.yaml` | what this machine can do: GPU, local inference, browser capture, backend roles |
| execution | *(none on NooPunk)* | NooPunk is user-activated; Laskin owns `config/execution/laskin-cron.yaml` |

`config/machines/noopunk.yaml` differs from Laskin's in exactly the ways the role
requires: `machine_class: laptop`, `browser_capture: true`, `cron: false`, a smaller
default batch, a bounded media-staging cache, and two named models.

## Model selection

Model selection is configuration, and it is explicit on both nodes.

| Mode | Model | When |
|---|---|---|
| **local** (default) | `gemma4:e2b` | lighter local testing on NooPunk's GPU |
| **cloud** | `gemma4:31b-cloud` | only when the user explicitly asks for the stronger model |

```bash
scripts/run_ai26_noopunk_analysis.sh --model local    # default
scripts/run_ai26_noopunk_analysis.sh --model cloud    # explicit opt-in
```

Three properties are enforced rather than documented-and-hoped:

- **cloud is never implicit.** There is no default that reaches the cloud model; the
  `--model` argument decides, and an unrecognised value is rejected instead of
  falling back.
- **`LLM_ALLOW_CLOUD_FALLBACK=0` on both paths.** A *local* run that silently
  escalated to the cloud model would be a rules fork and an unasked cost.
- **the selected model is printed and logged before any work is claimed**, so a run's
  provenance shows which provider actually ran.

## Running a batch

```bash
cd /path/to/LaclauGPT-Data-Analysis
export LACLAUGPT_ENV_FILE=/path/to/private/ai26/noopunk.env

scripts/run_ai26_noopunk_analysis.sh --dry-run          # validate config, claim nothing
scripts/run_ai26_noopunk_analysis.sh --max-tasks 1      # one item, for a quick test
scripts/run_ai26_noopunk_analysis.sh                    # default bounded batch (3)
scripts/run_ai26_noopunk_analysis.sh --model cloud --max-tasks 1
```

The default batch is **3**, deliberately smaller than Laskin's 10: a testing session
on a shared queue should not drain work the always-on node would otherwise have
processed. `--max-tasks` raises it when you mean to.

An OS-level lock (`flock`) prevents overlapping interactive runs, so double-invoking
the script exits cleanly rather than double-claiming.

### Required environment

The same required surface as Laskin — the shared distributed backend, not a local
substitute:

| Variable | Why it is required |
|---|---|
| `LACLAUGPT_RUN_ID` | one run identity per run, supplied per invocation |
| `LACLAUGPT_MONGODB_URI` | remote MongoDB; the shared corpus |
| `LACLAUGPT_REDIS_URL` | the shared task plane |
| `LACLAUGPT_S3_BUCKET` | CSC Allas / S3 object plane |
| `LACLAUGPT_LLM_ENDPOINT` | the local inference endpoint |

If any is missing the wrapper fails closed and claims nothing. There is no
local-only fallback on purpose: a workstation that quietly wrote to a local store
would fork the corpus while appearing to work.

## Stopping

The worker is **bounded**: it claims at most `--max-tasks` and exits on its own. There
is no daemon to stop. To interrupt a long interactive batch, send `SIGINT`/`SIGTERM`
to the process; a claimed-but-unfinished task is reclaimed by lease expiry
(`reclaim_idle_ms`), so an interrupted run does not strand work.

## Verifying a run

After a batch, confirm on the **shared** store, not locally:

1. the run's records carry `machine`/`execution` provenance showing the interactive
   workstation, not Laskin;
2. exactly one durable result exists per `idempotency_key` — re-running the same item
   must not double-write, and a duplicate concurrent claim is harmless by construction;
3. the model recorded in the result matches the mode you asked for (`gemma4:e2b` for
   local, `gemma4:31b-cloud` for cloud);
4. the item is visible on either node's dashboard, having arrived from the same store.

Existence of a process is not evidence of a completed batch; a healthy run shows a
*recent* result with provenance attached.

## What this runbook deliberately does not contain

No hostname, port, URI, bucket name, account, credential or private filesystem path.
Those live in `LaclauGPT-Private`. This file is the public procedure; the private
repository is the deployment.

## Related

- [`AI26_LASKIN_ANALYSIS.md`](AI26_LASKIN_ANALYSIS.md) — the always-on node
- [`AI26_DISTRIBUTED_WORKER.md`](AI26_DISTRIBUTED_WORKER.md) — worker contract
- [`DISTRIBUTED_PROJECT_STORAGE.md`](DISTRIBUTED_PROJECT_STORAGE.md) — the namespace contract
- `TomiToivio/LaclauGPT` → `docs/AI26_EXECUTION_ARCHITECTURE.md` — the two-machine contract
