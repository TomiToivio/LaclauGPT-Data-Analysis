# Optional Redis analysis task worker

Redis is an optional coordination layer. Basic/local analysis remains usable without the `redis` package or a Redis service.

The task envelope is deliberately reference-only. It carries `project_id`, `run_id`, task and idempotency identifiers, a canonical record reference, and schema/config/codebook revisions. Full research text, media, credentials, codebooks, or private configuration do not belong in Redis messages.

## Modes

### Direct/local

Use the normal analysis pipeline with CSV/SQLite/filesystem storage. `SqliteTaskStore` is available when an application wants durable local idempotency/retry history. No Redis import is required.

### Distributed

Configure MongoDB for durable state and Redis for coordination. The queue uses Redis Streams consumer groups. New tasks are claimed with `XREADGROUP`; abandoned pending tasks can be reclaimed with `XAUTOCLAIM` after a configured idle/lease period.

Durable result uniqueness is enforced before queue acknowledgement. A successful worker iteration therefore follows:

1. claim a reference-only task;
2. validate project/run/schema/config/codebook revisions;
3. check the durable idempotency key;
4. perform analysis;
5. persist the durable result in MongoDB;
6. acknowledge the Redis stream entry.

If a worker dies before step 6, another worker may reclaim the pending entry. The durable idempotency check prevents the retry from creating a second result.

Failures are written to durable storage. Redis only receives a compact dead-letter event after `max_attempts`; it is not the audit log.

## Environment

Use runtime environment/private configuration only:

```text
LACLAUGPT_PROJECT_ID=<project>
LACLAUGPT_RUN_ID=<run>
LACLAUGPT_REDIS_URL=<private redis URL>
LACLAUGPT_MONGO_URL=<private mongo URL>
LACLAUGPT_MONGO_DATABASE=laclaugpt
```

No endpoint or credential should be committed. The AI26 distributed worker in issue #15 builds on this generic adapter and adds the stricter frozen-run/model/private-config validation required for Roihu and the Linux server.

## Worker heartbeat

`TaskWorker.heartbeat()` writes an expiring Redis status value. This is liveness/coordination information only and must not be treated as durable research provenance.

## Design constraints

- Redis loss must not destroy durable results or failure history.
- Duplicate task delivery must not duplicate durable analysis results.
- Queue acknowledgement happens after the durable result write.
- Reclaim/retry is expected and safe.
- Direct mode remains functional without Redis.
- Messages contain references/identity only, never large research payloads or secrets.
