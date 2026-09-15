# LaclauGPT Data Analysis agent skill

Use this skill when an agent operates the Analysis module.

## Scope

This module owns canonical analysis over `CanonicalRecord`. Collection and Visualization are sibling modules. Do not reproduce their logic here.

## Deployment dimensions

Compose these independently:

- machine: `laptop`, `roihu`, `linux-server`, `custom`
- execution: `cli`, `slurm`, `cron`, `systemd`, `agent`, `custom`
- storage: `local`, `distributed`, `custom`
- LLM: `local-ollama`, `ollama-cloud`, `custom`

Convenience profiles are in `deployment.py`. They are suggestions, not hostname inference.

## Storage

Local means SQLite + CSV/JSONL/Pandas + local filesystem under private `data/`. Distributed means MongoDB for canonical records/queryable state, Redis for coordination/cache/worker messages, and S3-compatible storage such as CSC Allas for large objects. `source_url` remains canonical identity everywhere.

## Ollama

Supported example tags include `gemma4:e2b`, `gemma4:e4b`, `gemma4:12b`, `gemma4:26b`, `gemma4:31b`, and explicit cloud-only `gemma4:31b-cloud`. Never silently fall back to cloud. Cloud use requires explicit permission and must be represented in provenance.

## Operations

Use `laclaugpt_data_analysis.integrations.hermes` to:

1. inspect redacted effective deployment configuration;
2. validate capabilities/profile constraints;
3. explicitly discover Ollama models when requested;
4. dry-run/plan through the canonical runner;
5. launch analysis through the canonical runner;
6. inspect or resume runs;
7. export canonical results under `data/`;
8. stamp `hermes-agent` provenance.

Never bypass codebooks, canonical validation, review state, uncertainty, provenance or privacy checks.

## Agent-controlled pipeline

A normal same-host flow is:

```text
Collection/data -> configured Analysis collection_data_dir
                -> canonical Analysis runner
                -> Analysis/data exports
                -> configured Visualization input
```

Across machines, move canonical records through MongoDB or CSV/JSONL and referenced objects through S3/Allas. Redis coordinates work but does not carry a competing schema.

## Privacy

Real corpora, target lists, codebooks, researcher annotations, credentials, machine paths, CSC project identifiers and run state stay outside Git. Public SLURM/systemd/cron material uses placeholders only.
