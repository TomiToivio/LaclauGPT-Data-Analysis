# AI26 Laskin deployment and tick acceptance (#506)

This is an **operator checklist**, not evidence that a host deployment occurred. Phase 1 is
text-only: MongoDB canonical text/provenance and Redis coordination are mandatory;
S3/CSC Allas and media downloads are not. Do not change frozen sampling/codebooks.

## Durable per-tick telemetry

The canonical `scripts/run_ai26_laskin.sh` records one sanitized JSON object for
each exit into the private file
`$LACLAUGPT_PRIVATE_CONFIG_DIR/logs/ai26-analysis-ticks.jsonl`, or
`$LACLAUGPT_PRIVATE_ROOT/analysis/ai26/logs/ai26-analysis-ticks.jsonl`
when the private config directory is not explicitly configured. It includes UTC
timestamp, status, stage, exit code, check-only flag, worker/report statuses and
public Git SHA; it never stores credentials, prompts or source text.

Status values: `preflight_rejected` (exit 2 in preflight),
`already_running` (exit 3), `check_ok` (check-only 0),
`cycle_completed` (normal 0), `cycle_failed` (other nonzero).
If the private directory does not exist, stderr reports that persistence is
unavailable and the original command exit code is preserved. Non-zero telemetry
write errors likewise must not erase the original exit status.
The existing cron/wrapper scheduling contract remains unchanged.
An escalation threshold for repeated failures should be set with the host
operator after reviewing real alert volume, rather than silently inventing one.

A private, aggregate-only quick check:

```bash
python3 - "$LACLAUGPT_PRIVATE_ROOT/analysis/ai26/logs/ai26-analysis-ticks.jsonl" <<'PY'
import collections, json, sys
from pathlib import Path
rows = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
print(dict(collections.Counter(row["outcome"] for row in rows[-24:])))
PY
```

## Laskin acceptance (requires host access)

1. Outside the scheduled :05 tick, check no active writer and inspect `git status`,
   `git rev-parse HEAD`, `git rev-parse origin/main`, active cron target,
   virtualenv import path and private environment. Preserve local changes: never reset.
2. If clean and idle, fast-forward Analysis only to reviewed `main`; do not mutate
   Collection or Visualization checkouts to satisfy Analysis's drift gate.
3. Confirm text-only MongoDB/Redis preflight, and verify real canonical source text
   plus quotation/evidence provenance with aggregate/sanitized output only.
4. Execute `scripts/run_ai26_laskin.sh --check`, followed by one bounded,
   nonconcurrent run, with the cron :05 cycle avoided. Capture deployed SHA,
   local time, exit code, claimed/completed task counts, retries and errors.
5. In a controlled environment only, hold the lock while invoking the wrapper;
   verify exit 3 and `already_running` JSONL event, without disrupting live work.
6. Inspect JSONL evidence for every invocation, including a controlled failed
   preflight; ensure failed and skipped ticks cannot be read as successful work.
   Review post-stall backlog recovery, including retries and failures.
7. Set escalation thresholds with the operator, provide sanitized evidence on
   issue #506, then close it.

CI verifies repository semantics only. CI does not demonstrate Laskin deployment,
queue progress, source provenance, or monitoring delivery.
