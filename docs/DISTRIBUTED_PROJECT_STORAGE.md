# Distributed project storage

This module implements the shared LaclauGPT multi-project namespace in `schemas/distributed-project.schema.json`.

Set `LACLAUGPT_PROJECT_ID` to `ai26`, `ep24`, `brazil26`, `hungary26`, or another validated project ID. `Settings.distributed_namespace` derives the same Redis keys, MongoDB collections and S3 prefixes as Collection and Visualization.

## Redis-distributed analysis context

Redis is the control plane for small versioned configuration documents. Analysis workers can resolve:

```text
laclaugpt:<project>:manifest:current
laclaugpt:<project>:settings:analysis:current
laclaugpt:<project>:codebook:<name>:current
laclaugpt:<project>:stream:analysis-requested
laclaugpt:<project>:stream:analyzed
laclaugpt:<project>:worker:analysis:<worker_id>
```

A `current` key points to an immutable revision. The revision document follows the shared envelope: schema version, project ID, document type, name, revision, timestamp, SHA-256, payload and optional MongoDB/S3 references.

Codebooks small enough for normal configuration use may be stored directly in the Redis payload. Large codebooks, embeddings, model artifacts or corpora should live in S3/MongoDB and be referenced from the Redis document. Retrieved codebook/context material remains context rather than source evidence.

Workers must reject a control document, queue message or record whose `project_id` differs from their configured project.

## MongoDB analysis plane

One MongoDB database can host many projects through project-prefixed collections:

```text
ai26__records
ai26__annotations
ai26__runs
ai26__artifacts

ep24__records
ep24__annotations
hungary26__records
hungary26__annotations
```

`source_url` stays the stable cross-module identity. Analysis should preserve it unchanged. Recommended annotation identity is `(source_url, analysis_version)` when historical versions are retained.

Every MongoDB document should also contain `project_id` as a routing guard even though the collection name is project-specific.

## S3 / CSC Allas analysis plane

The shared bucket layout is:

```text
projects/<project>/canonical/
projects/<project>/media/
projects/<project>/transcripts/
projects/<project>/frames/
projects/<project>/analysis/
projects/<project>/codebooks/
projects/<project>/manifests/
projects/<project>/exports/
projects/<project>/runs/
```

This allows EP24 and Hungary26 Roihu jobs, AI26 server workers and future projects to share an Allas bucket safely. S3/Allas credentials, bucket names and endpoints remain private runtime settings.

## Distributed-worker startup

A worker should load `project_id`, resolve the manifest/settings/codebook revisions from Redis, validate hashes/schema/project identity, derive MongoDB/S3 names with `ProjectNamespace`, then join only that project's consumer groups. Redis messages contain lightweight record references rather than large binary or corpus payloads.
