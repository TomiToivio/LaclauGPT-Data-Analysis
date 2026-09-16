# Redis coordination for distributed analysis

Redis is optional coordination infrastructure for LaclauGPT. It is **not** the canonical research datastore and it is not the primary RAG/vector/graph memory store.

## Roles

Redis is used for three operational roles:

1. versioned distributed configuration;
2. reliable request/event messaging using Redis Streams;
3. task coordination using the existing Redis Streams worker queue.

Durable research data and analysis outputs remain in MongoDB/files/Parquet/object storage. Local analysis continues to work without Redis.

## Shared project namespace

All Redis keys are derived from `ProjectNamespace(project_id=...)` and therefore share the same project-scoped convention across modules.

Examples for `ai26`:

```text
laclaugpt:ai26:settings:analysis:<revision>
laclaugpt:ai26:settings:analysis:current
laclaugpt:ai26:stream:config-events
laclaugpt:ai26:stream:messages:rag
laclaugpt:ai26:stream:analysis:<run_id>:tasks
laclaugpt:ai26:worker:analysis:<worker_id>
laclaugpt:ai26:lock:<name>
```

The namespace contract accepts `collection`, `analysis`, `visualization`, `storage`, and `simulation` module names so modules do not invent incompatible Redis conventions.

## Distributed configuration

`coordination.ConfigRevision` is content-addressed. Its revision is the SHA-256 of canonical JSON configuration payload content.

`FileConfigStore` is the durable local implementation. It writes immutable revision snapshots plus a `current.json` pointer under:

```text
data/config/snapshots/<project>/<module>/
```

`RedisConfigStore` mirrors those revisions into Redis and emits a `config-events` stream event. The durable snapshot is written **before** Redis is updated, so Redis can never become the sole copy required for reproducibility.

Workers should resolve the desired configuration revision when a run starts and record that revision in run/task/result provenance. Long-running jobs should keep that pinned revision until an explicit safe batch boundary rather than silently adopting `current` halfway through a run.

Secrets and credentials do not belong in shared project configuration. Keep them in environment variables or ignored private runtime files.

## Messaging and RAG/agent requests

`MessageEnvelope` provides a shared request/event schema with:

```text
project_id
run_id
request_id
correlation_id
source_record_id
task_id
sender
recipient
message_type
created_at
config_revision
payload_ref
body
```

`RedisMessageBus` uses Redis Streams and consumer groups for replayable delivery. `InMemoryMessageBus` provides the same envelope contract for local/offline operation and tests.

Large research payloads must not travel through Redis. Store them in MongoDB/files/object storage and send `payload_ref` or another stable identifier. Inline message bodies are intentionally capped.

Typical flows:

```text
Visualization UI -> messages:rag -> retrieval service -> response/reference
analysis plugin   -> messages:rag -> vector/graph service -> response/reference
human validator   -> messages:analysis -> analysis worker
agent              -> messages:analysis -> selected pipeline service
```

Requests and responses should preserve the same `correlation_id` so interaction history is auditable.

## Task queue and leases

The existing `task_queue.py` Redis implementation uses Streams consumer groups for atomic claiming. Pending entries are reclaimed using `XAUTOCLAIM` after a configured idle period, which provides the worker-crash lease/reclaim mechanism.

`TaskEnvelope` carries project, run, config and codebook revisions plus an idempotency key. `MongoTaskStore` applies a unique `(project_id, run_id, idempotency_key)` result constraint so durable duplicate results are rejected even if a task is redelivered.

The AI26 distributed worker persists the durable result before acknowledging the Redis task, records failures, increments retry attempts, and sends exhausted tasks to a dead-letter stream.

Worker heartbeats already support arbitrary metadata. `WorkerCapability` standardizes useful routing metadata such as machine/platform, GPU, memory, available models and plugins. A scheduler may use this metadata for heterogeneous routing, but scientifically meaningful results must not depend on a worker heartbeat remaining in Redis.

## Local mode

No Redis server is required for ordinary local analysis:

```python
settings.redis_url is None
```

then `config_store_from_settings(settings)` uses durable local files and `message_bus_from_settings(...)` uses the in-memory bus. Existing local/direct task execution remains available.

## Redis-enabled mode

Install remote dependencies and provide a private Redis URL:

```bash
pip install -e '.[remote]'
export LACLAUGPT_REDIS_URL='redis://...'
```

Do not expose Redis unauthenticated to the public Internet. Credentials and private endpoints must remain outside the repository.

## Reproducibility rule

**Redis coordinates distributed analysis; durable stores preserve data/results; pinned configuration revisions preserve semantics and reproducibility.**
