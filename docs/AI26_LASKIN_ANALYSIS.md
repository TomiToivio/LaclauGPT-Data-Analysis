# AI26 analysis on Laskin

Operator guide for the unattended AI26 analysis run on **Laskin**, a Linux
server that drains the distributed analysis queue from cron once per hour.

Private settings, credentials and research data never live in this repository.
The real machine configuration lives in the private repository; this guide
describes the public contract and the operator workflow.

```text
Laskin
  cron (hourly at :05)
    └─ bounded AI26 analysis worker (claims N tasks, then exits)
          ├─ reads ready handoffs from remote MongoDB
          ├─ stages referenced multimodal objects from CSC Allas / S3
          ├─ runs the AI26 stages on local gemma4:12b (http://127.0.0.1:11500)
          └─ persists results + provenance to MongoDB

Collection is staggered separately at :10 and media processing at :30.
Shared services: remote MongoDB · remote Redis · CSC Allas/S3 · one ai26 namespace
```

Machine identity is execution provenance. It is never part of scientific source
identity, and Laskin does not create its own database, bucket or codebook.

## Canonical lookup order

Before guessing AI26 settings, inspect:

1. `docs/AI26_REFERENCE_CASE.md`
2. `codebooks/public/ai26_v2.yaml` and `codebooks/public/seed_ai_formations.md`
3. `config/projects/ai26.yaml` — study semantics for this run
4. `config/machines/laskin.yaml` + `config/execution/laskin-cron.yaml`
5. `docs/AI26_DISTRIBUTED_WORKER.md` and `docs/ANALYSIS_RUNTIME.md`
6. private runtime copies under the private root, when authorised

## Layered configuration

The repository composes three independent layers. Keep their responsibilities
separate — do not put study semantics in a machine file or scheduling in a
project file.

| Layer | Public template | Owns |
|---|---|---|
| project | `config/projects/ai26.yaml` | study semantics, codebook/context/prompt selection, stages |
| machine | `config/machines/laskin.yaml` | capability: local Ollama, model, backend roles, paths |
| execution | `config/execution/laskin-cron.yaml` | cadence, bounds, overlap lock, logging |

Effective settings for this run:

```text
project          ai26
machine          laskin (linux-server)
execution        cron
llm mode         local-ollama
model            gemma4:12b
endpoint         http://127.0.0.1:11500
records          mongodb      objects  s3      cache  redis
stages           Laclau/Mouffe/Palonen + DNA statement coding + Critical AI
cadence          hourly at :05, bounded drain
```

Cloud inference is explicitly disabled: a research run must never silently
change inference provider mid-corpus.

## Expected private layout

The real runtime lives in the private repository (never committed publicly):

```text
<private-root>/analysis/ai26/
  laskin.env          runtime contract incl. credentials (0600, uncommitted)
  analysis.json       frozen private analysis configuration
  codebook.json       effective merged codebook
  run-manifest.json   hash-bound run manifest
  codebooks/          private overlays
  logs/               operational logs
  run/                lock files
  cache/media-staging/  staged multimodal objects
```

For the current Laskin deployment, operational logs should remain under the
private runtime tree, for example:

```text
/mnt/workspace/LaclauGPT-Private/runtime/ai26/analysis/ai26-laskin-analysis.log
```

## Install

```bash
cd /path/to/LaclauGPT-Data-Analysis
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[remote,ollama,dev]'
```

`remote` provides MongoDB/Redis/boto3; `ollama` provides the local client. The
`dev` extra is installed on Laskin because the documented verification runs the
full repository test suite and therefore needs the same scientific/RDF test
dependencies as CI.

Verify the checkout before enabling cron:

```bash
.venv/bin/python -m pytest
```

A runtime-only installation may omit `dev` when no repository tests will be run.

## Ollama

Laskin serves the analysis model locally:

```bash
curl -s http://127.0.0.1:11500/api/tags | head -c 200
ollama pull gemma4:12b       # only if the model is missing
```

The wrapper fails fast when the endpoint is unreachable or the model is absent,
so a misconfigured endpoint is caught during preflight rather than mid-corpus.

## Freeze the run

A distributed run is reproducible only if its private inputs are pinned by hash
before any worker starts. Re-freeze whenever the analysis config, the codebook
or the public revision changes:

```bash
.venv/bin/laclaugpt-freeze-ai26 \
  --private-root /path/to/private-root/analysis/ai26 \
  --public-codebook codebooks/public/ai26_v2.yaml \
  --private-overlay /path/to/private-root/analysis/ai26/codebooks/ai26_overlay.yaml \
  --analysis-config /path/to/private-root/analysis/ai26/analysis.json \
  --run-id <shared-run-id> \
  --model gemma4:12b
```

Omit `--private-overlay` when none exists. The tool writes the effective
codebook and a `run-manifest.json` binding project, run, schema, model and the
public Git revision. The worker **fails closed** when any pinned hash disagrees,
so configuration drift is a hard error rather than a silent change of meaning.

For Laskin, `scripts/install_ai26_laskin_cron.sh` is also the deployment/update
boundary. It re-freezes the manifest against the current checkout and runs one
cron-equivalent bounded cycle successfully before it installs or replaces the
cron entry. This preserves the strict Git-SHA guard without leaving a stale
manifest after every merge.

## Preflight

```bash
.venv/bin/laclaugpt-preflight
```

Reports the composed configuration and sanitized connectivity for MongoDB,
Redis, the object store and Ollama. It never prints credentials or full
authenticated URLs. Exit code `0` is healthy, `2` reports problems.

## Run once

```bash
./scripts/run_ai26_laskin.sh --check          # preflight only, no work claimed
./scripts/run_ai26_laskin.sh --debug --once   # verbose, one bounded cycle
./scripts/run_ai26_laskin.sh --once           # normal bounded cycle
```

The wrapper resolves the repository, loads the **private** environment itself
(cron inherits no interactive shell), verifies Ollama, takes `flock`, runs a
bounded batch and exits. Exit codes:

```text
0  success
2  configuration or preflight failure
3  another tick holds the lock (benign; the previous run is still working)
```

A cycle that attempts work and completes none of it exits non-zero, so cron or
monitoring can detect a broken analysis path instead of silently accepting it.

## Debug mode

```bash
LACLAUGPT_DEBUG=1 ./scripts/run_ai26_laskin.sh --once
```

Debug mode adds operational detail: composed profile, connectivity checks,
selected record, stage transitions with timings, prompt resource id/version/hash,
staging status, model/endpoint, persistence state and final status.

Credentials, tokens and authenticated URLs are redacted by pattern. **Full prompt
and evidence bodies are withheld** even in debug mode because they may contain
research data; emitting them requires the explicit opt-in:

```bash
LACLAUGPT_TRACE=1 LACLAUGPT_DEBUG=1 ./scripts/run_ai26_laskin.sh --once
```

Do not leave trace mode on for scheduled runs.

## Multimodal staging from Allas

Canonical records may reference images, video, audio, frames or transcripts held
in CSC Allas/S3. Before any multimodal model call the worker stages each
referenced object into the private cache:

- an existing verified cache entry is reused rather than re-downloaded;
- size is checked, and the record's checksum when one is supplied;
- a **retriable** transport failure aborts the task so it retries, instead of
  producing a degraded result;
- a **permanently missing** object is recorded and the record still analyses
  text-only;
- object identity and staging outcome are recorded in provenance without
  credentials.

Staging **never** mutates or deletes the canonical remote object: Allas holds
the canonical copy, the cache is a local performance concern.

Cache pruning is operator-configurable. On Laskin it is **disabled by decision**
(staged objects are retained until cleared manually), so monitor the cache
directory size and clear it deliberately:

```bash
du -sh <private-root>/analysis/ai26/cache/media-staging
```

## Enable cron

Preferred installation is the idempotent helper:

```bash
cd /mnt/workspace/LaclauGPT-Data-Analysis
LACLAUGPT_PRIVATE_ROOT=/mnt/workspace/LaclauGPT-Private/runtime/ai26 \
  bash scripts/install_ai26_laskin_cron.sh
```

Before modifying crontab the helper loads the private runtime contract,
re-freezes `run-manifest.json` to the current public Git SHA, and executes one
normal `run_ai26_laskin.sh --once` cycle. It installs the schedule only if that
cycle exits `0`. If configuration, Ollama, storage, or the refreshed manifest is
invalid, installation stops and the existing cron entry is left untouched.

The helper installs exactly one tagged entry and replaces older invocations of
the same wrapper. The resulting canonical entry is:

```cron
5 * * * * /bin/bash /mnt/workspace/LaclauGPT-Data-Analysis/scripts/run_ai26_laskin.sh >> /mnt/workspace/LaclauGPT-Private/runtime/ai26/analysis/ai26-laskin-analysis.log 2>&1 # LaclauGPT AI26 analysis
```

This is intentionally staggered from the Collection jobs (`:10` collect,
`:30` media). `LACLAUGPT_MAX_TASKS` bounds each cycle, and `flock` prevents
accidental overlap.

If installing manually, back up the crontab first:

```bash
crontab -l > /mnt/workspace/LaclauGPT-Private/runtime/ai26/analysis/crontab.backup.$(date -u +%Y%m%dT%H%M%SZ).txt
crontab -e
```

Cron is the only scheduler. The worker is bounded, so nothing keeps a perpetual
process or an internal scheduler alive.

## Disable cron

```bash
crontab -l | grep -v 'run_ai26_laskin.sh' | crontab -
```

## Verify cron actually runs

Cron provides a minimal environment, which is the usual cause of a job that
works by hand but not on schedule:

```bash
env -i LACLAUGPT_PRIVATE_ROOT=/mnt/workspace/LaclauGPT-Private/runtime/ai26 \
  /bin/bash /mnt/workspace/LaclauGPT-Data-Analysis/scripts/run_ai26_laskin.sh --once

tail -50 /mnt/workspace/LaclauGPT-Private/runtime/ai26/analysis/ai26-laskin-analysis.log
crontab -l | grep run_ai26_laskin
```

Confirm that an unattended tick creates new results in the effective AI26
analysis collection (for the deployed run this is `ai26__analyzed`) and that a
known failing cycle produces a non-zero exit.

## Status and health

```bash
crontab -l | grep run_ai26_laskin
tail -50 /mnt/workspace/LaclauGPT-Private/runtime/ai26/analysis/ai26-laskin-analysis.log
.venv/bin/laclaugpt-preflight
```

The presence of a lock file alone is not evidence of a live job; `flock`
ownership is authoritative. Repeated exit code `3` means a previous hourly tick
is still running; inspect backlog, `LACLAUGPT_MAX_TASKS`, and the log.

## Recovery after a failed run

1. Read the tail of the log and identify the failing stage.
2. If a hash or public Git SHA mismatch is reported, stop the schedule and run
   the deployment helper again after confirming the intended config/codebook.
   The helper re-freezes and proves one cycle before restoring cron. Do not edit
   manifest hashes by hand.
3. If a backend is unreachable, restore it before re-enabling cron; the worker
   fails closed rather than writing partial results.
4. If a task exhausted its attempts it is dead-lettered with its durable failure
   history preserved; requeue through the normal task contract rather than
   editing Redis by hand.

## Safe update / restart

```bash
crontab -l | grep -v 'run_ai26_laskin.sh' | crontab -   # pause
cd /mnt/workspace/LaclauGPT-Data-Analysis
git pull --ff-only origin main
.venv/bin/python -m pip install -e '.[remote,ollama,dev]'
.venv/bin/python -m pytest
.venv/bin/laclaugpt-preflight
LACLAUGPT_PRIVATE_ROOT=/mnt/workspace/LaclauGPT-Private/runtime/ai26 \
  bash scripts/install_ai26_laskin_cron.sh
```

The install helper now performs the required re-freeze after every code update
and refuses to install cron unless a bounded production-path cycle exits `0`.
The public Git SHA therefore remains a meaningful provenance invariant rather
than a manual trap after each merge.

## Test one synthetic record end to end

Use a synthetic/public-safe record rather than private research material:

1. Publish one synthetic canonical record with a `handoff.status=ready`
   envelope for the run id.
2. Run `./scripts/run_ai26_laskin.sh --debug --once`.
3. Confirm the log shows: record resolved, staging outcome, stage transitions
   with prompt identity, persistence, and a final status.
4. Confirm the durable result in MongoDB carries the run id, model, public Git
   SHA and config/codebook hashes.
5. Re-run and confirm the idempotency key prevents a duplicate scientific
   result.

## Where results and provenance live

- **MongoDB** — durable canonical records, analysis results and failure history.
- **CSC Allas/S3** — large artifacts under the shared project prefix.
- **Redis** — coordination only: task stream, leases, heartbeats. Redis is never
  the canonical schema, and losing Redis must not erase a completed result.
- **Provenance** — every model-assisted stage records prompt id/version/hash,
  rendered-prompt hash, model, configuration revision, codebook revision and
  the public Git SHA. Machine identity stays provenance-only.

## Privacy boundaries

- never commit credentials, connection strings, access keys or cookies;
- keep logs, cache and staged media under the private root;
- do not expose private source lists or row-level research data in any public
  artifact;
- treat prompt/evidence bodies as research data: `LACLAUGPT_TRACE=1` is a
  deliberate opt-in;
- the six formation anchors are provisional sensitising concepts, never actor
  identities or ground truth.
