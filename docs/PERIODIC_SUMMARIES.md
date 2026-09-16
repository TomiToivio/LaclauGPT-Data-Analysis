# Periodic discourse / ideology summaries

`laclaugpt_data_analysis.periodic_summary` is the canonical temporal aggregation layer for researcher-facing discourse monitoring and downstream Visualization.

It supersedes the old idea that a “daily report” is only a top-count list. `reporting.build_daily_report()` remains available for compatibility, while `PeriodicDiscourseSummary` carries interval-aware statistics, temporal deltas, provenance, evidence references, scoped summaries and bounded historical context.

## Scientific contract

A periodic summary describes how a discourse is moving. It does not equate frequency with hegemony, centrality with nodal status, ambiguity with empty/floating signification, or negative sentiment with antagonism. Formation, frontier, affect and signifier-role outputs remain candidates unless the underlying canonical analysis provides the appropriate evidence.

Previous summaries are **historical context, never current-source evidence**. `summary_context_item()` marks them `context_not_evidence`, and `inject_summary_context()` puts them into the existing `PipelineContext.situational_context` with the summary ID and SHA-256 in provenance.

## Canonical entity

`PeriodicDiscourseSummary` contains:

- stable `id` derived from project + scope + window + revision inputs;
- project and `SummaryScope`;
- timezone-aware `window_start` / `window_end` and interval seconds;
- source-data cutoff;
- previous summary IDs;
- typed `PeriodicSummaryStatistics`;
- researcher-facing Markdown narrative;
- evidence/source references;
- aggregation/model/prompt/config/codebook provenance.

The deterministic aggregate is valid without an LLM. Optional `synthesize_narrative()` uses the versioned `periodic_summary.narrative:v1` prompt plus `laclau.system:v1`; prompt and rendered hashes are recorded.

## Statistics

The first implementation aggregates:

- record coverage, authors, platforms/sources, languages and incomplete records;
- signifiers and provisional formations with document frequency, normalized frequency, source/author coverage, formation distribution and previous-window delta;
- canonical `Us`, `Them`, frontier and affect candidates;
- canonical relation/articulation edges and temporal deltas;
- simple discourse-graph degree and degree deltas;
- descriptive change categories (`new`, `increasing`, `decreasing`, `stable`, `disappearing`, `frontier_shift`).

These are descriptive aggregate signals. They do not promote graph or frequency statistics into theoretical conclusions.

## Windows

The default interval is 24 hours.

`latest_completed_window()` returns the most recently completed interval, suitable for real-time cron/orchestration. `corpus_windows()` uses source/event timestamps and therefore works for historical Roihu/Slurm reprocessing regardless of wall-clock time or input order. Empty intervals can still be summarized explicitly by calling `build_periodic_summary()` with no records in the window.

## Scopes / grouping

Every run can produce an overall summary plus grouped summaries. `grouped_summaries()` supports canonical dimensions including:

- `signifier`
- `formation`
- `author` / `actor`
- `source` / `platform`
- `arena`
- `language`
- `country` / `region`
- `topic` / `theme`
- `document_type` / `source_type`
- compatible raw-metadata keys

No AI26-specific labels are hard-coded. AI26, EP24, Hungary26 and other studies use their own codebooks/config/context.

## CLI

Installed command:

```bash
laclaugpt-summarize-period \
  --input data/canonical.jsonl \
  --output data/periodic-summaries.jsonl \
  --project AI26
```

Historical corpus-time catch-up:

```bash
laclaugpt-summarize-period \
  --input data/canonical.jsonl \
  --output data/periodic-summaries.jsonl \
  --project EP24 \
  --all-windows \
  --group-by formation \
  --group-by author
```

Explicit regeneration window:

```bash
laclaugpt-summarize-period \
  --input data/canonical.jsonl \
  --output data/periodic-summaries.jsonl \
  --project Hungary26 \
  --from 2026-04-01T00:00:00+00:00 \
  --to 2026-04-02T00:00:00+00:00
```

### Cron

Cron remains deployment/orchestration, not scientific logic. A local real-time deployment can call the same command once per day, for example:

```cron
15 0 * * * cd /srv/laclaugpt-data-analysis && . .venv/bin/activate && laclaugpt-summarize-period --input data/canonical.jsonl --output data/periodic-summaries.jsonl --project AI26
```

The default CLI window is the last *completed* UTC 24-hour interval, so a rerun describes the same deterministic window. Persistent deployment code should store/upsert summaries through `PeriodicSummaryRepository` to get stable-ID idempotency.

## Storage

`PeriodicSummaryRepository` uses the existing `RecordStore` port. This allows `CsvStore`, `SqliteStore`, or the configured `MongoStore`/`record_store(settings, name="periodic_summaries")` without creating a second storage architecture.

Rows contain a flat identity/index surface plus canonical `payload_json`; this keeps nested statistics portable across CSV/SQLite/MongoDB. MongoDB remains durable storage when configured. Redis may coordinate scheduling/leases through the existing task/coordination layer but is not the durable summary store.

## Temporal memory

Use `PeriodicSummaryRepository.latest()` or `.history(limit=N)` with the same project and scope. Historical summaries can be converted to a normal context-memory item with `summary_context_item()` and therefore participate in existing context-profile budgets.

For batch data, request summaries whose `window_end` is at or before the record being analysed. Never inject a later real-time summary into an earlier historical EP24/Hungary26 document.

## Visualization / drill-down

Visualization should consume the JSON-compatible `PeriodicDiscourseSummary` contract rather than importing aggregation internals. `evidence_refs`, metric-level evidence references, source URLs, window/scope identity and provenance allow drill-down from temporal claim → aggregate → canonical record/evidence.

## Tests

`tests/test_periodic_summary.py` is fully offline and covers corpus-time windows, completed real-time windows, temporal deltas, grouped scopes, frontier aggregation, summary-context evidence separation, provenance, idempotent local persistence and project isolation.
