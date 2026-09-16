# AI26 distributed analysis worker

This is the bounded integration-test worker for the AI26 distributed deployment. It consumes the generic Redis task contract from issue #16 and runs the existing canonical LaclauGPT analysis pipeline. Redis coordinates work, MongoDB holds durable record/result state, and each host talks to its own local Ollama endpoint.

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

The private runtime directory must contain the frozen analysis configuration and codebook used for the run. The public worker records only their SHA-256 fingerprints. It does not log or persist private configuration contents in Redis messages.

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

Workers fail closed if the project, run, schema, model, config hash or codebook hash does not match. The manifest, private config and codebook should live in the private runtime/config location rather than this repository.

## Collection -> Analysis handoff

Collection persists canonical records at the top level of the project-scoped `<project>__records` MongoDB collection and adds a `handoff` envelope. Analysis reads only records with `handoff.status=ready` and the same frozen run ID. `--seed-ready` mirrors a bounded set of those durable handoffs into the Analysis Redis task stream. Redis receives only `source_url`, handoff/idempotency identity and frozen revisions, not the research payload.

The worker orders the bounded seed by Collection's handoff priority, newest publication time and stable source identity. The Collection `handoff_key`, which incorporates source revision, becomes the Analysis idempotency key.

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

## Task and result semantics

A Redis task contains references and frozen revisions, not full research payloads. The worker resolves the canonical record from Collection's MongoDB `records` collection by stable `source_url`, validates the task against the run manifest, and calls `run_canonical_pipeline(..., project_profile="ai26")`.

The durable result is keyed by `(project_id, run_id, idempotency_key)` in MongoDB. Queue acknowledgement happens only after the durable write, so a killed worker can leave a pending task that another worker later reclaims without creating a second durable result.

Worker heartbeat/status is ephemeral Redis state. Run/model/schema/config/codebook/worker provenance is attached to durable task results.

## Current integration boundary

This first worker slice covers text/canonical-record analysis available from MongoDB and the existing canonical pipeline. Large artifacts remain referenced externally by the canonical record and Collection's Allas/S3 handoff. A bounded live smoke test should verify media staging for media-bearing records before expanding beyond text-ready records.
