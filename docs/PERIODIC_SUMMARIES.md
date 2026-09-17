# Periodic discourse / ideology summaries

`laclaugpt_data_analysis.periodic_summary` is the canonical 24-hour situational-awareness layer for Data Analysis. It produces one report contract for two consumers: human researchers/dashboard code and the downstream analysis pipeline.

The report is deliberately split into an authoritative deterministic aggregate plus a compact Markdown narrative. Optional LLM synthesis can rewrite the narrative, but it cannot replace or alter the aggregate statistics.

## Scientific contract

A periodic summary is a research instrument, not an ideology classifier or popularity chart. The implementation preserves these semantic safeguards:

- frequency != hegemony;
- co-occurrence != articulation;
- network community != ideological formation;
- negative sentiment != antagonistic frontier;
- sentiment/emotion != affective investment;
- topic != discourse/frame/ideology by default.

Previous summaries are **historical context, never evidence for the current window**. `summary_context_item()` marks them `context_not_evidence`. `inject_summary_context()` stores report ID and SHA-256 in pipeline provenance.

## Architecture

The production flow is:

```text
canonical analysed records
  -> exact half-open 24h window [start, end)
  -> optional generic scope filter
  -> deterministic single-pass aggregation
  -> like-for-like comparison with previous scope
  -> optional versioned-prompt LLM narrative
  -> persisted PeriodicDiscourseSummary
  -> dashboard/UI + bounded pipeline context
```

Generation remains in Data Analysis. Visualization should only list, display, filter, request/rerun and drill into persisted report objects.

## Canonical entity and compatibility

`PeriodicDiscourseSummary` remains the public report model. Version 2 is additive: old stored payloads are still accepted by Pydantic because newly introduced fields have defaults.

Each report contains:

- stable logical ID derived from project + scope + window;
- schema/report-generator version;
- project and generic `SummaryScope`;
- timezone-aware window start/end;
- source-data cutoff and generation timestamp;
- previous comparable report IDs;
- deterministic typed statistics;
- Markdown narrative;
- evidence/source references;
- config/codebook/model/prompt provenance when available.

The ID intentionally **does not include config or codebook revision**. Rerunning the same logical project/scope/window replaces the same report instead of creating duplicates. Revisions remain in provenance so the exact generation conditions are auditable.

`PeriodicSummaryRepository.save()` is idempotent by report ID and continues to use the existing `RecordStore` abstraction.

## Windows

The default interval is exactly 24 hours.

`latest_completed_window()` selects the last completed UTC interval for cron/real-time operation. `corpus_windows()` derives windows from source/event timestamps, which is appropriate for historical EP24/Hungary26/Roihu reprocessing regardless of wall-clock ingestion time.

Window membership is half-open: `start <= timestamp < end`. Missing source timestamps are excluded from the aggregate and counted in coverage metadata.

## Deterministic statistics

Aggregation is performed in a small number of passes over the selected records. Document frequency is accumulated while visiting each record instead of rescanning the corpus once per label.

The report includes:

- analysed record count and total records considered;
- missing timestamps;
- failed/incomplete analyses;
- distinct authors/actors;
- source/platform distribution;
- language distribution;
- signifier count + document frequency + normalized frequency;
- formation distribution;
- `Us`, `Them` and frontier candidates;
- affect outputs when present;
- topic and theme distributions;
- explicit canonical relations/articulations and deltas;
- graph degree and degree deltas from explicit relations;
- new/increasing/decreasing/stable/disappearing change categories;
- bounded evidence references for drill-down.

The deterministic aggregate is authoritative. Narrative generation is downstream presentation.

## Scopes

The default report is `project + window + overall`.

`SummaryScope` is generic. Supported canonical dimensions include:

- `author` / `actor`
- `formation`
- `signifier`
- `topic` / `theme`
- `source` / `platform`
- `arena`
- `language`
- `country` / `region`
- `document_type` / `source_type`
- compatible source `raw_metadata` keys

Like-for-like comparison is mandatory: `author=alice` compares only with an earlier `author=alice` report, never with the overall report.

## CLI

Installed command:

```bash
laclaugpt-summarize-period \
  --input data/canonical.jsonl \
  --output data/periodic-summaries.jsonl \
  --project AI26
```

The default invocation selects the latest completed 24-hour window. Existing reports in `--output` are loaded first so trend deltas compare against persisted prior periods and reruns replace the same logical report.

Scoped report:

```bash
laclaugpt-summarize-period \
  --input data/canonical.jsonl \
  --output data/periodic-summaries.jsonl \
  --project AI26 \
  --scope formation=accelerationism
```

Other examples:

```bash
laclaugpt-summarize-period --input data/canonical.jsonl --output data/periodic-summaries.jsonl --project AI26 --scope author=alice
laclaugpt-summarize-period --input data/canonical.jsonl --output data/periodic-summaries.jsonl --project AI26 --scope signifier=AGI
```

Explicit reproducible historical window:

```bash
laclaugpt-summarize-period \
  --input data/canonical.jsonl \
  --output data/periodic-summaries.jsonl \
  --project EP24 \
  --start 2024-05-20T00:00:00+00:00 \
  --end 2024-05-21T00:00:00+00:00
```

Legacy `--from` / `--to` aliases remain supported.

Historical catch-up and grouped products:

```bash
laclaugpt-summarize-period \
  --input data/canonical.jsonl \
  --output data/periodic-summaries.jsonl \
  --project EP24 \
  --all-windows \
  --group-by formation \
  --group-by author
```

`--scope` and `--group-by` are intentionally mutually exclusive for one invocation: `--scope` requests one specific product, while `--group-by` discovers all values for selected dimensions.

## Cron

Cron owns scheduling only. Scientific/report logic stays in the CLI/API.

Example daily production invocation:

```cron
15 0 * * * cd /srv/laclaugpt-data-analysis && . .venv/bin/activate && laclaugpt-summarize-period --input data/canonical.jsonl --output data/periodic-summaries.jsonl --project AI26
```

Running the command twice for the same project/scope/window is safe because report identity is stable and the output writer upserts by report ID.

## Python / agent / dashboard interfaces

Normal Python and agent tools should call:

- `build_periodic_summary(...)` for one explicit scope/window;
- `grouped_summaries(...)` for an overall report plus discovered grouped scopes;
- `PeriodicSummaryRepository.save/latest/history` for persistence and temporal lookup;
- `summary_context_item(...)` or `inject_summary_context(...)` for downstream LLM context.

Dashboard/UI integrations should consume the JSON-compatible report model and may expose:

- list by project/window/scope;
- Markdown narrative;
- structured statistical families and deltas;
- evidence refs for drill-down;
- user-requested scoped reports;
- authorized reruns that call Data Analysis rather than duplicating generation logic.

## Situational context injection

Pipeline injection is deliberately smaller than the human report. `context_payload()` contains:

- explicit `historical situational context; not current-source evidence` label;
- report ID/window/scope;
- coverage notes;
- major changes;
- top signifiers/formations/frontiers/topics;
- important relation changes;
- short narrative excerpt.

`context_text(max_chars=N)` bounds the representation. The full Markdown remains available to researchers and dashboards.

For historical corpora, only inject reports whose `window_end` is at or before the record timestamp. Never inject a later real-time report into an earlier historical document.

## Previous history

The immediately previous comparable report supplies deltas. `history_depth` defaults to seven reports and records every previous report ID actually supplied as historical context. Comparison itself remains against the immediately previous comparable report to keep deltas interpretable.

## Scalability and limits

`PeriodicSummaryLimits` controls presentation/context growth without changing the source records:

- `max_evidence_refs_per_metric` (default 50)
- `max_labels_per_family` (default 100)
- `max_relations` (default 250)
- `max_context_chars` (default 12,000)
- `max_narrative_chars` (default 20,000)
- `history_depth` (default 7)
- minimum prominence count/document-frequency fields for callers and narrative policy

Aggregation now accumulates count and document-frequency maps during record traversal. It no longer computes document frequency by scanning every record once for every discovered label. This removes the pathological `records x labels` behaviour in the former implementation.

LLM synthesis receives aggregate JSON plus bounded historical aggregate context, not every underlying record.

## Provenance

Deterministic reports record, where available:

- schema version;
- report generator version;
- project;
- scope;
- window start/end;
- source-data cutoff;
- records considered/selected;
- generation timestamp;
- previous report IDs;
- configuration revision;
- codebook revision;
- configured limits.

When `synthesize_narrative()` is used, existing prompt-library provenance plus provider/model metadata are added to the same report provenance object.

## Prompt library

Optional LLM narrative synthesis uses `periodic_summary.narrative:v1` and `laclau.system:v1`. The task prompt explicitly separates current deterministic aggregates from prior historical context, forbids unsupported trends, requires coverage/uncertainty notes, and preserves the semantic safeguards above.

## Evidence and drill-down

Metric-level `evidence_refs`, report-level `evidence_refs`, explicit source URLs, window/scope identity and provenance support the dashboard path:

```text
narrative claim / statistic -> aggregate metric -> evidence ref -> canonical record/source evidence
```

Previous-summary text must never be used as a current-window evidence reference.

## Tests

`tests/test_periodic_summary.py` covers:

- corpus-time and latest-completed windows;
- exact half-open 24-hour selection;
- missing timestamps;
- empty windows;
- source/language distributions;
- failed/incomplete analyses;
- deterministic document frequency;
- previous-period deltas;
- author/formation/signifier scopes;
- like-for-like history provenance;
- stable report identity across config revisions;
- bounded evidence/context;
- context/evidence separation;
- JSON/dashboard serialization;
- idempotent persistence and project isolation;
- semantic safeguards in generated narrative.

The aggregation implementation is single-pass per selected record for label/document-frequency accumulation, so runtime grows with records plus emitted labels/relations rather than repeated corpus rescans per label.
