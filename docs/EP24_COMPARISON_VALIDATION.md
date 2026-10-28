# Offline EP24 current vs legacy comparison (#399)

This tool compares **metadata only** for two completed, independently executed runs. It does not execute EP24, access remote services, or establish scientific equivalence.

Each input JSON manifest must contain `pipeline_id` (`ep24` or `ep24-legacy`), a unique `run_id`, `input_ids` (list of stable scientific record identifiers), and `stage_statuses` (mapping of stage to status). Optional `upstream_sha`, `model`, `config_sha256`, and `codebook_sha256` are copied to the report.

```bash
python scripts/compare_ep24_manifests.py \
  --current /private/ep24-current-run.json \
  --legacy /private/ep24-legacy-run.json \
  --output /private/ep24-comparison.json
python -m pytest -q tests/test_compare_ep24_manifests.py
```

The command rejects a wrong pipeline id, duplicate input identifiers, differing frozen input sets, malformed stage status maps, or shared run identity. These checks **cannot prove** that MongoDB collections, Redis tasks, or Allas keys are isolated. Before enabling either pipeline on shared infrastructure, confirm the actual effective namespaces and durable index policy. Never run historical scripts against production output targets.

## Remaining acceptance work

- Execute the two genuine upstream EP24 implementations with their respective dependencies on one authorized frozen sample.
- Prove independent Redis, MongoDB, and Allas namespaces and idempotent retries from live results.
- Compare per-record output schemas and scientific contents beyond stage status; characterize model and prompt differences.
- Execute AI26 on Roihu alongside Laskin under an authorized CSC account and collect observed resource and correctness evidence for #390.

Until those checks succeed, **#399 and #390 must remain open**.
