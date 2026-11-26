# AI26 graph publication and capacity-aware daily throughput

Issues #577, #578 and #579. These tools do not modify the locked Phase 1 paper
or the seven human-owned scientific steps. DNA and SNA are optional Phase 2
products. The locked step 6 and step 7 functions currently raise
`NotImplementedError`. The study owner must implement or authorize their
specific scientific logic, or provide already coded inputs. No support tool
may bypass those functions by guessing stance, identity or social ties.

## Daily analysis throughput (#577)

Run on the authorized host using the private analysis worker log:

```bash
python -m laclaugpt_data_analysis.ai26_daily_throughput \
  --log "$AI26_ANALYSIS_LOG" --day "$(date +%F)" --timezone Europe/Helsinki
```

Use completed tasks per day, not the count of exit-0 cron ticks. Duplicates are
reported separately. The day is the worker summary's end date in the specified
timezone; summaries are not exact per-task commit times. A measured zero is
different from no observations (null); missing summaries, including killed
workers, can undercount. The durable results store is authoritative for exact
per-task completion times. Include this output in the daily operations ledger.

Exit 75 is a capacity park, not a failed document or a successful analysis.
Inspect the existing scheduler, model residency and GPU memory read-only. Do
not terminate other researchers' processes, change their allocations, switch
models or enable cloud inference without the study owner's explicit decision.
Resume the existing scheduled worker when its approved capacity returns.
Qualify any continuity claim with observed daily throughput; do not alter the
locked paper automatically.

## Explicit producer input and publication (#578/#579)

The publication command consumes a private JSON object with two arrays:
`statements` (existing interoperability DiscourseStatement objects) and
`relations` (existing SNARelation objects). Provide both arrays even if one is
empty. Each item must carry exact canonical IDs, source_url, evidence IDs and
provenance ID; DNA also requires an explicit qualifier. Rejected/superseded
statements and co-occurrence-as-social-tie inputs are refused. The input
provider is responsible for evidence validity and review; this adapter checks
structure and provenance presence, not scientific truth. Provisional review
status is preserved, not promoted. If both arrays are empty, the command fails
instead of claiming success.

Use the private runtime boundary and the actual frozen run/codebook/prompt
identifiers. Example (environment variables are private operator inputs):

```bash
python -m laclaugpt_data_analysis.ai26_graph_publish \
  --input "$AI26_NETWORK_INPUT" --output "$AI26_NETWORK_OUTPUT" \
  --run-id "$AI26_NETWORK_RUN_ID" \
  --codebook-version "$AI26_CODEBOOK_VERSION" \
  --prompt-version "$AI26_PROMPT_VERSION"
```

The output is an atomic owner-only JSON AnalyticalGraph v1.0.0. It can be
uploaded using the existing Visualization network artifact input. DNA is the
existing actor → statement → concept projection with explicit qualifier and
review status; SNA retains observed directedness, weight and source identity.
No label-based identity merge or inferred association is performed. Graph
metadata records the run and exact version references; edge provenance retains
run ID, method, codebook reference, source locator and evidence IDs.

For first-time Mongo publication, explicitly source the authorized private
configuration (`LACLAUGPT_MONGODB_URI` and `LACLAUGPT_MONGODB_DATABASE`) and
repeat the above command with `--mongo`. This uses the existing MongoGraphStore
and `kg_meta`/`kg_nodes`/`kg_edges`. Run with one publisher and pause graph
readers during initial publication: the existing store does not provide a
multi-collection atomic transaction. The same input and version set are
idempotent. A changed snapshot is refused rather than leaving stale edges;
coordinate replacement with the Visualization owner. JSON export can be
regenerated atomically independently of Mongo. No rows are deleted by this
tool.

Verify the dashboard's actual shared source window on port 8504: both layers
when covered by evidence, correct source/evidence IDs and review state, and
honest zero counts for absent coverage. Do not publish private data to Git.
The issues stay open until real producer inputs, capacity and live host
verification are available.
