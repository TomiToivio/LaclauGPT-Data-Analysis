# #429 — the ready frame is not the analysed frame

## The property that is broken

The AI26 seed walk orders the ready frame by
`(handoff.source_priority ASC, handoff.published_at DESC, source_url ASC)` and stops as soon as
`LACLAUGPT_MAX_TASKS` tasks have been published. That is a correct order and a correct stop; the
defect is that the two compose badly at this corpus size.

Measured frame (2026-11-11, `ai26`, 4,708 ready records):

| position | tier |
|---|---|
| 1 – 2,126 | `source_priority = 1` (rss, web) |
| 2,127 – 3,536 | `source_priority = 2` (bluesky, mastodon, arxiv) |
| 3,537 – 4,708 | `source_priority = 3` (x — closed stratum, #401) |

First never-analysed record by platform in that order: `rss` 4, `web` 1,410, `bluesky` 2,127,
`mastodon` 2,293, `arxiv` 2,563, `x` 3,540.

A cycle spends its ten publications before it can reach position 2,127. `examined` sat at
1,850 → 2,130 → 2,130 across three cycles: the walk reaches the tier boundary and stops there,
every cycle, forever. Intake into tier 1 is of the same order as cycle capacity, so the boundary
does not move.

## Why it matters

`paper/PHASE_1_PAPER.md` §4.2 draws the evaluation sample from **analysed** documents, stratified
by arena, source type, language and predicted formation. A platform whose analysed share falls
while its ready count rises is not an operational wobble: it is a coverage property of the sample,
and it is invisible in every per-cycle log line because each cycle reports a healthy
`published: 10`.

The 416 never-analysed non-X records are not random — 307 are Bluesky and 295 were published in
October. That is the old tail of one platform, and Bluesky's analysed share fell 72.0 % → 71.3 %
in 24 h while its ready count grew.

## What this repository now does about it

**It measures the property.** `tools/ai26_ready_frame_audit.py` reproduces the worker's own sort
order, reports per-platform analysed share, the position of each platform's first never-analysed
record, and the backlog by publication month. It is read-only and never publishes a task.

```bash
cd /mnt/workspace/LaclauGPT-Data-Analysis
set -a; . ./.env; set +a
.venv/bin/python tools/ai26_ready_frame_audit.py            # table + behind-note
.venv/bin/python tools/ai26_ready_frame_audit.py --json      # machine-readable
.venv/bin/python tools/ai26_ready_frame_audit.py --fail-under 0.80   # exit 1 when a platform is behind
```

A position larger than `LACLAUGPT_MAX_TASKS` is the whole diagnosis in one number: that platform
cannot be reached by a single cycle of the current order.

## Decision

**The priority-ordered frame is accepted as a Phase 1 limitation, and the limitation is recorded
rather than discovered.** The evaluation sample is described as *documents the pipeline reached*,
not *the ready corpus*, for as long as the audit shows a platform below the threshold.

This is the second of the two resolutions the issue allows. It is chosen because it is the one
that can be stated truthfully today: the corpus is still growing, the tier sizes are still moving,
and a seeding change made under those conditions would be an untested guess about a live queue.

The `x` stratum stays out of the verdict — it was closed deliberately (#401) — but it is still
printed, because a closed stratum that is visible is different from one that has quietly gone
missing.

## Thresholds that reopen this

Reopen the seeding change if any of these holds:

- a non-closed platform's analysed share is below `0.80` for two consecutive daily measurements;
- the never-analysed pool grows between two daily measurements;
- a platform's first never-analysed position stays above `LACLAUGPT_MAX_TASKS` for seven days.

The third is the sharpest: it says the order cannot reach the tail at all, which is exactly the
state measured on 2026-11-11.

## What is deliberately not done here

The seeding walk itself (`distributed_worker.py`) is not changed by this commit. A bounded
backfill that reuses the `LACLAUGPT_HANDOFF_PLATFORM` scoping idea for a **date window** — walk
`published_at ASC` inside a window instead of a platform — is the implementation path when one of
the thresholds above fires. It is a change to a live queue's only source of work, so it needs the
measurement above to prove it worked, which is why the measurement lands first.

## Paper

`paper/PHASE_1_PAPER.md` lives in the paper repository, not here. The sentence to add to §4.2 —
in the author's own words, not generated — is that the evaluation sample is drawn from analysed
documents and that per-platform analysed shares are reported with the sample.
