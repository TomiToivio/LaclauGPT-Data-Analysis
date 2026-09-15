# Deployment profiles and Hermes operation

LaclauGPT Data Analysis uses one canonical analysis engine and one canonical data contract in every environment. Deployment changes execution, storage topology and model routing, not record semantics.

## Deployment matrix

| Case | Machine | Execution | Storage | Suggested Ollama model |
| --- | --- | --- | --- | --- |
| Research laptop | `laptop` | `cli` | `local` | `gemma4:e4b`, optionally `gemma4:12b` |
| Research laptop with explicit cloud permission | `laptop` | `cli` | `local` | `gemma4:31b-cloud` |
| CSC Roihu / HPC | `roihu` | `slurm` | local or distributed | `gemma4:26b`, optionally `gemma4:31b` |
| Persistent Linux server | `linux-server` | `cron` / `systemd` | local or distributed | `gemma4:12b` |

These are recommendations, not hostname rules. Operators may override model, storage and execution independently. `gemma4:e2b`, `gemma4:e4b`, `gemma4:12b`, `gemma4:26b` and `gemma4:31b` are local examples. `gemma4:31b-cloud` requires both `llm=ollama-cloud` and explicit cloud permission. There is no silent local-to-cloud fallback.

## Local topology

```text
LaclauGPT-Data-Collection/data/
        -> configured collection_data_dir
LaclauGPT-Data-Analysis/data/
        -> CSV / JSONL / SQLite / local artifacts
LaclauGPT-Data-Visualization/data/
```

Collection paths are configured. Analysis never guesses sibling repository locations.

## Distributed topology

```text
canonical records -> MongoDB
coordination/cache/worker state -> Redis
large files/artifacts -> S3-compatible storage / CSC Allas
manual fallback -> CSV / JSONL
```

MongoDB `_id` is not canonical identity. Redis is coordination infrastructure, not a semantic schema. S3/Allas stores referenced objects. Canonical `source_url` remains the semantic identity in every topology.

## Safe Roihu SLURM template

Generate a template with `render_slurm(...)`, then add site-specific account, partition and scratch settings privately. Public code contains no CSC username, project ID, `/scratch/...` path or credential.

Example shape:

```bash
#!/bin/bash
#SBATCH --job-name=laclaugpt-analysis
#SBATCH --gres=gpu:1
#SBATCH --time=04:00:00
# Add site-specific account/partition directives privately.
set -euo pipefail
mkdir -p data/logs data/runs data/tmp
python -m your_private_analysis_runner
```

Large-corpus runners should chunk work, persist run state under `data/runs/`, and support resume/retry. An explicitly configured external scratch directory is allowed, but must never be hard-coded into public code.

## Linux scheduling

`render_cron(...)` creates a lock-protected scheduled command writing logs to `data/logs/`. `render_systemd(...)` generates a `oneshot` service and persistent timer. Both are templates only and execute nothing during import or CI.

## Ollama routing and provenance

`DeploymentProfile` selects a model explicitly. `resolve_profile_model(...)` validates cloud permission and does not probe hardware. The older `pick_model(...)` local-availability router remains for existing callers and is forbidden from selecting cloud models.

Every agent-triggered/model-assisted run should record model tag, backend, endpoint, machine, execution mode, cloud permission and caller in canonical provenance/model-run metadata.

## Hermes

`integrations/hermes.py` exposes a small agent-facing surface:

- inspect a redacted effective profile;
- validate deployment configuration;
- explicitly discover local Ollama models when requested;
- dry-run/plan a canonical analysis run;
- launch through an injected canonical runner;
- inspect, resume and export runs;
- stamp agent provenance without changing `source_url`.

Hermes never gets a separate analysis implementation. It calls the same runner/configuration/canonical APIs used by human and scheduler operation.

Agent exports must stay under the private `data/` runtime boundary. Real credentials, codebooks, corpora, researcher notes, runtime state and study-specific paths remain outside Git.

## Provenance callers

Typical caller metadata:

- interactive researcher: `human-cli`
- SLURM/cron/systemd: `scheduler`
- Hermes or another compatible agent runtime: `hermes-agent`

The caller changes provenance, not data meaning.
