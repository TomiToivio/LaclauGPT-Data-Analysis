# AI26 distributed analysis worker

This is the bounded integration-test worker for the AI26 distributed deployment. It consumes the generic Redis task contract and runs the existing canonical LaclauGPT analysis pipeline. Redis coordinates work, MongoDB holds durable record/result state, Collection-owned large media/artifacts remain referenced in CSC Allas/S3, and each host talks to its own local Ollama endpoint.

Do not use this document to launch a full AI26 corpus run. Start with a small private test selection.

## Runtime contract

The worker requires these values from the environment or another private runtime mechanism:

```text
LACLAUGPT_PROJECT_ID=ai26
LACLAUGPT_RUN_ID=<shared run id>
LACLAUGPT_PRIVATE_CONFIG_DIR=<private runtime directory>
LACLAUGPT_MONGODB_URI=<private MongoDB URI>
LACLAUGPT_REDIS_URL=<private Redis URL>
OLLAMA_HOST=<host-local Ollama endpoint>
```

For this integration test the worker also enforces:

```text
LLM_MODE=local
LLM_ALLOW_CLOUD_FALLBACK=0
LACLAUGPT_OLLAMA_MODEL=gemma4:12b
```

The private runtime directory must contain the frozen run manifest, analysis configuration and codebook used for the run. The public worker records only SHA-256 fingerprints for the private files. It does not log or persist private configuration contents in Redis messages.

## Frozen run manifest

Create a private JSON manifest for the bounded run with this shape:

```json
{
  "project_id": "ai26",
  "run_id": "<shared run id>",
  "schema_version": "1.2.0",
  "config_sha256": "<sha256 of private analysis config>",
  "codebook_sha256": "<sha256 of private codebook>",
  "model": "gemma4:12b",
  "public_git_sha": "<Data-Analysis git sha>"
}
```

Workers fail closed if the project, run, schema, model, public Git revision, config hash or codebook hash does not match. The worker resolves the checked-out Git revision itself; deployments where `.git` is unavailable may set `LACLAUGPT_PUBLIC_GIT_SHA` explicitly to the exact frozen revision.

The manifest itself must also live below `LACLAUGPT_PRIVATE_CONFIG_DIR`. This keeps one clear runtime boundary for all frozen run material.

## Collection -> Analysis handoff

Collection persists canonical records at the top level of the project-scoped `<project>__records` MongoDB collection and adds a `handoff` envelope. Analysis reads only records with `handoff.status=ready`, the same frozen run ID, and `handoff.published_at >= 2026-09-01T00:00:00+00:00`. This mirrors the AI26 Collection policy instead of silently widening the corpus at analysis time.

`--seed-ready` mirrors a bounded set of those durable handoffs into the Analysis Redis task stream. Redis receives only `source_url`, handoff/idempotency identity and frozen revisions, not the research payload.

The worker orders the bounded seed by Collection's `source_priority`, newest publication time and stable source identity. Collection is responsible for the source-priority tiers, including X-last behavior. Elites, grassroots and parliamentary material remain part of the same AI26 run and retain their arena metadata in the canonical record.

The Collection `handoff_key`, which incorporates source revision, becomes the Analysis idempotency key.

## Linux server

Install the package with the remote and Ollama extras, export the runtime variables above, and run a bounded worker:

```bash
python -m pip install -e '.[remote,ollama]'

export LACLAUGPT_MACHINE=linux-server
export LACLAUGPT_EXECUTION=systemd
export LACLAUGPT_STORAGE=distributed
export LACLAUGPT_DATA_BACKEND=mongodb
export LACLAUGPT_CACHE_BACKEND=redis

laclaugpt-analysis-worker \
  --run-manifest "$LACLAUGPT_PRIVATE_CONFIG_DIR/run-manifest.json" \
  --private-config "$LACLAUGPT_PRIVATE_CONFIG_DIR/analysis.json" \
  --codebook "$LACLAUGPT_PRIVATE_CONFIG_DIR/codebook.json" \
  --seed-ready \
  --max-tasks 25
```

The process is suitable for a service/cron wrapper. Keep secrets in the host's private environment file or secret store, not in a tracked service unit. In a multi-worker run, normally only one bounded launcher needs to use `--seed-ready`; additional workers can consume the shared task stream without reseeding.

## CSC Roihu

Use `scripts/roihu/ai26_worker.sbatch.example` as the public skeleton. Supply project-specific account paths, environment activation, Ollama startup and credentials from private runtime configuration. The worker contract itself is the same as on the Linux server.

Each machine uses its own `OLLAMA_HOST`; there is no requirement for Roihu and the Linux server to share one Ollama service.

## Task, retry and result semantics

A Redis task contains references and frozen revisions, not full research payloads. The worker resolves the canonical record from Collection's MongoDB `records` collection by stable `source_url`, validates the task against the run manifest, and calls `run_canonical_pipeline(..., project_profile="ai26")`.

The durable result is keyed by `(project_id, run_id, idempotency_key)` in MongoDB. Queue acknowledgement happens only after the durable write, so a killed worker can leave a pending task that another worker later reclaims without creating a second durable result.

Handled failures are requeued as a new reference-only task with `attempt + 1`, then the old Redis message is acknowledged. The bounded worker defaults to three attempts; the final failure is written to durable failure history and dead-lettered. This avoids the previous failure mode where a reclaimed message retained `attempt=1` forever.

A process killed before it can requeue/ack leaves the original message pending. Redis lease expiry allows another worker to reclaim it. MongoDB's unique `(project_id, run_id, idempotency_key)` result index keeps the durable result idempotent even when delivery is duplicated around a crash boundary.

Worker heartbeat/status is ephemeral Redis state. Run/model/schema/config/codebook/worker provenance is attached to durable task results.

## Allas / large-artifact boundary

The Analysis worker does not copy media payloads through Redis or MongoDB. Media-bearing canonical records keep their deterministic Collection-owned Allas/S3 references and checksums. Analysis consumes those references only when an analysis stage actually requires the media. This preserves the four-layer record while keeping large artifacts in object storage rather than the coordination plane.

For the first bounded distributed test, prefer text-ready records. Exercise one small media-bearing record separately before increasing the batch size.

## Verification checklist

Before expanding beyond the bounded test, verify on the actual private infrastructure:

1. The same frozen `run_id`, schema/config/codebook hashes and public Git SHA are accepted on both Roihu and the Linux server.
2. Each host resolves its own `OLLAMA_HOST` and serves `gemma4:12b`; cloud fallback remains disabled.
3. A bounded `--seed-ready --max-tasks 25` run seeds only post-2026-09-01 AI26 records in Collection priority order.
4. Kill one worker after claim but before acknowledgement, wait past the reclaim threshold, and confirm another worker completes the task.
5. Force a deterministic handler failure and confirm attempts advance to the dead-letter limit rather than remaining at attempt 1.
6. Confirm only one durable MongoDB result exists for an idempotency key after duplicate delivery/reclaim.
7. Confirm durable provenance contains run ID, worker ID, model, public Git SHA, schema version and private config/codebook hashes.
8. Confirm one media-bearing record retains a valid Allas/S3 reference/checksum and does not move its payload through Redis.

The repository tests cover the offline invariants. Steps requiring the private MongoDB/Redis/Ollama/Allas deployment remain a deliberately bounded live smoke test, not a public CI test.
