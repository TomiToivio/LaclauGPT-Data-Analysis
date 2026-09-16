# AI26 analysis on CSC Roihu and Laskin

This runbook deploys **one AI26 scientific analysis pipeline** to two unattended execution environments:

```text
localhost/laptop  -> development / small manual runs
CSC Roihu         -> bounded Slurm GPU batches
Laskin            -> bounded hourly cron cycles

all three -> same AI26 MongoDB + Redis + CSC Allas/S3 namespace
```

Machine identity is provenance only. Do not create separate AI26 databases, Redis projects, buckets, codebooks or scientific settings for Roihu and Laskin.

## Canonical lookup order

Before an agent guesses or reconstructs AI26 settings, inspect these current repository resources first:

1. `docs/AI26_REFERENCE_CASE.md`
2. `codebooks/public/seed_ai_formations.md` and codebooks explicitly referenced by the reference case
3. `docs/AI26_DISTRIBUTED_WORKER.md`
4. `docs/ANALYSIS_RUNTIME.md`
5. `docs/REDIS_COORDINATION.md` and `docs/REDIS_TASK_WORKER.md`
6. ignored/private runtime copies under `data/config/ai26/` when authorized
7. legacy repositories only for archaeology when current material is genuinely missing

For a real run, `run-manifest.json`, `analysis.json` and `codebook.json` are private frozen runtime inputs. Their hashes plus the public Git SHA are part of the worker contract. A worker fails closed if these do not match the frozen manifest.

## Shared private runtime

Create an ignored runtime directory on each machine, for example:

```text
data/config/ai26/
  run-manifest.json
  analysis.json
  codebook.json
  roihu.env      # on Roihu
  laskin.env     # on Laskin
```

Start from:

```text
deployment/ai26.roihu.env.example
deployment/ai26.laskin.env.example
```

Both private env files must resolve to the same logical values for:

```text
LACLAUGPT_PROJECT_ID=ai26
LACLAUGPT_RUN_ID=<same frozen run>
LACLAUGPT_MONGODB_URI=<same remote service>
LACLAUGPT_MONGO_DATABASE=<same database>
LACLAUGPT_REDIS_URL=<same remote service>
LACLAUGPT_S3_BUCKET=<same Allas bucket>
LACLAUGPT_S3_PREFIX_ROOT=projects
```

Never commit credentials, private hostnames, tokens, unpublished codebooks or frozen private manifests.

## Storage and coordination contract

MongoDB stores canonical records, durable analysis results, failures and idempotency state. Redis coordinates task streams, reclaim, heartbeats and configuration. Redis loss must not erase completed analysis. CSC Allas stores source media and larger analysis artifacts using deterministic project-oriented keys such as `projects/ai26/...`.

The artifact adapter supports text, binary objects, file upload and file download. Plugins or preprocessing code that require a referenced media object should stage it into ignored scratch space and preserve the source object reference/checksum in provenance. Do not embed large media blobs in MongoDB or Redis.

## Laskin: one manual cycle

Install the repository and remote dependencies in the supported virtual environment, then copy the Laskin example profile to ignored runtime configuration.

```bash
cd /path/to/LaclauGPT-Data-Analysis
source .venv/bin/activate
pip install -e '.[remote,ollama]'
cp deployment/ai26.laskin.env.example data/config/ai26/laskin.env
# edit only the ignored copy
bash scripts/run_ai26_laskin_analysis.sh
```

The wrapper:

- loads secrets from the ignored env file;
- pins `project_id=ai26` and the private run manifest;
- uses remote MongoDB, Redis and Allas;
- uses `flock` to prevent overlap;
- reclaims abandoned Redis work after the configured idle threshold;
- processes a bounded number of tasks and exits;
- records a worker identity beginning with `laskin-cron-`;
- relies on the worker's durable-write-before-ack contract.

## Laskin: hourly cron

A safe staggered example is:

```cron
15 * * * * cd /path/to/LaclauGPT-Data-Analysis && bash scripts/run_ai26_laskin_analysis.sh >> data/logs/ai26-laskin-analysis.log 2>&1
```

Cron is the scheduler. Do not wrap this command in another perpetual scheduler.

Inspect remotely:

```bash
crontab -l
tail -n 100 data/logs/ai26-laskin-analysis.log
```

The presence of the lock file alone is not evidence of a live job; `flock` ownership is authoritative.

## Roihu: one Slurm batch

Copy the public template if private Slurm account/partition/resource overrides are required. Keep those overrides outside Git.

```bash
cd /path/to/LaclauGPT-Data-Analysis
cp deployment/ai26.roihu.env.example data/config/ai26/roihu.env
# edit ignored copy
export LACLAUGPT_REPO_ROOT="$PWD"
export LACLAUGPT_ENV_FILE="$PWD/data/config/ai26/roihu.env"
sbatch scripts/roihu/ai26_worker.sbatch.example
```

The template loads the ignored env file, sets the Roihu/Slurm execution profile, uses the same frozen run inputs, and emits a worker ID containing `SLURM_JOB_ID` and the optional array task ID. The scientific pipeline is the same `laclaugpt-analysis-worker` used elsewhere.

Resource lines in the checked-in `sbatch` file are examples. Adapt GPU partition, account, memory, CPUs and wall time in a private copy if the CSC allocation requires different values.

Inspect jobs and logs with normal Slurm tooling:

```bash
squeue -u "$USER"
sacct -j <job-id>
```

Use Slurm arrays only for bounded independent workers. Redis already owns task distribution, so an array must not pre-partition the same records independently.

## Model/provider provenance

A frozen run must make its model/provider choice explicit. The current AI26 integration worker requires the frozen manifest model to match the supported local model contract and rejects silent cloud fallback. Machine-specific endpoints may differ, but a run may not silently change semantic configuration halfway through processing.

The broader project supports configurable model families including `gemma4:12b`, `gemma4:31b-cloud`, and `gemma4:e2b`; any future relaxation of the AI26 worker's current local-model restriction must keep provider/model differences explicit in provenance.

## Allas staging example

Analysis code should use the repository artifact abstraction instead of raw boto3 calls. Conceptually:

```python
store = artifact_store(settings)
local_path = store.download_ref(media.object_ref, settings.data_path("tmp", "input.bin"))
# process local_path
artifact_ref = store.upload_file(f"runs/{run_id}/derived/result.bin", output_path)
```

The resulting S3 reference belongs in canonical/plugin provenance or artifact metadata. Large payloads do not belong in Redis messages.

## Redis and Mongo inspection

The shared namespace is derived from the same project ID. For AI26, workers use the same Redis stream family and Mongo project collections regardless of machine. Use existing project tooling or private administrative clients to inspect task/result state without printing credentials.

Key invariants:

- only one worker should own a pending stream entry at a time;
- expired pending work can be reclaimed;
- completed durable results are keyed idempotently by run/project/task identity;
- a duplicate worker that sees an already completed idempotency key acknowledges without creating a second scientific result.

## Safe restart/requeue

Laskin: stop the cron entry or let the bounded process exit, update code/environment, verify the frozen public Git SHA still matches the manifest, then invoke the wrapper manually before re-enabling cron.

Roihu: cancel/requeue through Slurm as appropriate. An interrupted task remains recoverable through Redis pending-entry reclaim; already durable Mongo results are not recomputed as distinct records.

Do not change `analysis.json`, `codebook.json`, public Git SHA or model in place under an existing run ID. Freeze a new run manifest/revision instead.

## Private live smoke test

1. Confirm localhost, Roihu and Laskin use `project_id=ai26` and the same run ID.
2. Confirm both remote profiles resolve to the same MongoDB, Redis and Allas project namespace without printing secrets.
3. Confirm the frozen config/codebook/public Git hashes validate.
4. Seed a small bounded set of ready canonical handoffs.
5. Run `scripts/run_ai26_laskin_analysis.sh`; confirm a bounded task completes.
6. Submit `scripts/roihu/ai26_worker.sbatch.example`; confirm another compatible task completes.
7. Inspect Mongo durable results for worker/model/config/codebook provenance.
8. Stage one small public-safe object from Allas and upload one derived artifact through the artifact adapter.
9. Kill/restart a worker and verify reclaim does not create duplicate durable results.
10. Deliberately alter a copied config or codebook and confirm the worker fails closed against the frozen manifest.
11. Verify logs contain no credentials, private payload dumps or complete authenticated URLs.

## Troubleshooting

If a worker fails before claiming tasks, check the private runtime paths, project/run ID, Git SHA and config/codebook hashes first. If task claiming fails, check Redis connectivity and namespace. If canonical resolution or durable result writes fail, check MongoDB. If media/artifact staging fails, check the S3 endpoint/bucket credentials and object reference. If model calls fail, check the configured provider endpoint and ensure silent cloud fallback is not enabled.

The operational rule is simple: **one AI26 scientific run, many workers, shared durable state, explicit machine provenance.**
