# Naming a provider-capacity outage (#577)

A zero in the daily throughput ledger has three possible causes — the worker is broken, the provider has no
capacity, or nothing was scheduled — and they need different responses. This tool reads the AI26 tick
journal and states which one it is, with the outage's start, duration and reason mix.

It exists because #577 is the case where the answer took 18 hours to become legible: every cycle parked
correctly (exit 75, `reason=no_gpu_capacity`), no task completed, and the only artefact that said so in one
line was a stall alert that named the reason but not the duration.

## Usage

```bash
python -m laclaugpt_data_analysis.ai26_capacity_outage \
    --journal /path/to/ai26-ticks.jsonl
```

```
provider capacity outage ongoing: 15 parked cycle(s) over 16.05 h, last completed cycle
2026-11-25T18:38:40+00:00, 3 completed of 18 cycle event(s)
  2026-11-25T20:48:45+00:00 -> 2026-11-26T12:41:11+00:00 (15.87 h, 15 cycles, {'provider_unavailable': 15})
```

`--json` emits the same report as a structured object, including every interval.

## Exit statuses

| Status | Meaning |
| --- | --- |
| `0` | no ongoing capacity outage in the journal (it may have ended, or never happened) |
| `3` | an outage is ongoing: the last interval has capacity parks and no completed cycle since |
| `2` | the journal could not be read |

A cron wrapper can therefore surface an ongoing outage without parsing English.

## What it will not say

- **That the provider is healthy now.** The journal records what happened when a cycle ran; it cannot see the
  GPU between cycles. A `0` exit means "the last cycle completed", not "capacity is available".
- **How many tasks completed per day.** That is
  [`ai26_daily_throughput`](../../src/laclaugpt_data_analysis/ai26_daily_throughput.py), which counts worker
  summaries; the two answer different questions and are meant to be read together — throughput for the day's
  output, this report for why a day's output is zero.
- **That the park should be lifted.** Per the study owner's decision of 2026-11-26 the worker keeps
  `gemma4:12b`, keeps parking, and waits for an authorized GPU allocation. This tool reports; it does not
  retry, requeue or reallocate anything.

## Semantics worth knowing before quoting a number

- An empty journal is *unknown*, not zero: counts come back as `null` with a coverage note.
- `already_running` cycles are listed as reasons inside an interval but do not on their own make it a
  capacity outage — a held lock can coexist with a perfectly healthy endpoint.
- A `check_ok` preflight is not a cycle and neither extends nor ends an interval.
- A completed cycle ends the interval, so a park that recovered is reported as **ended**, with the interval
  that contained it still listed.
- Malformed journal lines are counted and reported, never silently dropped: a report that undercounts
  quietly is worse than one that admits the gap.

## Reading it against the GPU

Pair the report with the host-side evidence that explains it, which only the host can produce:

```bash
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
curl -s http://127.0.0.1:11434/api/ps
curl -s http://127.0.0.1:11435/api/ps
```

An ongoing outage plus `{"models":[]}` on both endpoints is a capacity/allocation condition, not a pipeline
defect; that distinction is the whole point of the exercise, and it is why this tool refuses to guess the
former from the latter.
