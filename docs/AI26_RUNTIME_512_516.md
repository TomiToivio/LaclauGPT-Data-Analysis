# AI26 runtime follow-ups (#512–#516)

The canonical Laskin wrapper now has one per-invocation JSONL journal writer.
It uses the analysis venv where possible, with a Python 3.10-compatible fallback.
A successful --check writes exactly one check-only record. The prior split
tick_status and trap writers caused competing records and paths.

The private journal writes ai26-analysis-alert.json beside the JSONL file.
A host watchdog can poll escalation, skip_streak, reject_streak, outcome,
and timestamp_utc without reading private source data.

Set LACLAUGPT_AI26_SKIP_ALERT_THRESHOLD=3 and
LACLAUGPT_AI26_REJECT_ALERT_THRESHOLD=2 only after adopting the operator
policy. Zero (default) disables escalation, not journaling. Checks do not
reset failure streaks because they do not process tasks; completed cycles do.
No automatic process termination or external alert delivery is enabled.

#512: A 9000-second ceiling is not a progress detector. Do not kill
workers based only on stale result/failure write timestamps. Add a
per-task heartbeat and distinguish long model inference from a hung worker
before enabling an automatic timeout. Host acceptance is pending.

#515: The worker logs MongoDB persistence failure exception class, operation
and server code. Full exception messages may embed private source records
and are deliberately excluded. Diagnose live code, validators/indexes, BSON
size and document shape before changing schemas or retry policy.

These are repository changes only. No Laskin deployment, production DB
migration or bounded-cycle host verification has been performed.
