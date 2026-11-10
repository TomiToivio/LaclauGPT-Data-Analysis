# AI26 prompt budget: the decision (#425)

> **Decision: do not raise the output ceiling, and do not lower the source cap.** Keep the 48k budget
> with 20k source and 12k previous-analysis. The truncation cascade has subsided, and the number that
> still matters is a different one: **18.6% of prompt builds drop a context section to fit.** Make that
> visible and reversible rather than paying for it silently.

Measured with `tools/ai26_prompt_budget_audit.py` against the Laskin worker log, 2026-11-10.

---

## 1. What the numbers say

| day | cycles | completed | retry | dead | trunc 4k | 8k | 16k | prompt builds | starved |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11-06 | 12 | 112 | 8 | 0 | 9 | 9 | 0 | 226 | 140 |
| 11-07 | 12 | 111 | 9 | 0 | 24 | 23 | 0 | 233 | 176 |
| 11-08 | 13 | 104 | 22 | 4 | 33 | 31 | 0 | 230 | 126 |
| 11-09 | 12 | 115 | 5 | 0 | 23 | 18 | 0 | 238 | 76 |
| 11-10 | 7 | 63 | 7 | 0 | 5 | 3 | 0 | 136 | 48 |

**9.0 completions per cycle over 56 cycles**, against a theoretical 10. The 4–6 window the issue was
opened for was 11-08: 8.0 per cycle with 22 retries and 4 dead-letters. It has not recurred.

The counts in the issue (47 / 64 / 41 / 8 truncations per day) count *events*; the table above counts
them **by rung**, which is why the figures differ. Both are the same log.

## 2. The finding that changes the question

The issue framed the choice as *raise the output ceiling* or *lower the source cap*. Neither addresses
the structural cost that is still present every day:

> **198 of 1,063 prompt builds (18.6%) omitted `memory` and/or `rag` because the budget was already
> spent** — 15 and 18 respectively on 11-10 alone.

The budget is not being blown by the *answer*; it is being consumed by **input**: a 20k lossless dump of
the canonical record plus a 12k lossless dump of every earlier stage output. When those two fill 32k of
the 48k, the sections that carry prior context are dropped, and the model analyses a document while
forgetting what the project knows about it.

Raising the output ceiling cannot fix that — it moves the answer boundary, not the input one. Lowering
the source cap would fix it by giving the analyst less to read, which is the trade-off the issue was
right to call a human decision.

## 3. Why "no change" is the right change right now

1. **Truncation is no longer the bottleneck.** 5 events on 11-10, 8 the day before, against 64 on 11-08.
2. **The ladder's top rung is unused.** 101 uses of `num_predict=16384` in the whole log, none of them
   in the last four days. Raising the ceiling would buy nothing measurable.
3. **Starvation is a quality question, not a throughput one.** It deserves a deliberate policy, not a
   side effect of a fix for retries.
4. **Every knob is already an environment variable**, so a decision taken now is reversible in one
   line without a code change.

## 4. If context must always be present — the cheapest lever

`previous_analysis` is a **raw dump of earlier stage outputs**, capped at 12,000 characters. It is the
largest block that is not the document itself, and the least irreplaceable: the pipeline can re-read a
stage output, but it cannot re-invent the project's memory of the case.

```bash
# free 6k for memory and rag: keep 20k of source, halve the previous-analysis dump
export LACLAUGPT_PROMPT_CAP_PREVIOUS_ANALYSIS=6000
```

| Option | Effect | research cost |
| --- | --- | --- |
| `LACLAUGPT_PROMPT_CAP_PREVIOUS_ANALYSIS=6000` | frees room for `memory` + `rag` | earlier stage outputs are summarised less completely |
| `LACLAUGPT_PROMPT_BUDGET_CHARS=64000` | fits everything | exceeds the 16k-token context at 4 chars/token; the model may truncate at the server instead, which is worse because it is invisible here |
| `LACLAUGPT_PROMPT_CAP_CURRENT_SOURCE=12000` | frees 8k for context | the analyst sees 40% less of each document — a real research change |

**Recommendation:** if the freeze (#81) needs every analysis to carry memory and RAG, take the first
option and re-run the audit after 24 hours. If it does not, change nothing and watch the number.

## 5. When to revisit

Reopen the question if any of these holds for three consecutive days:

- truncation events exceed **5% of prompt builds**
- dead-letters are non-zero for three cycles in a row
- starvation exceeds **40% of prompt builds** (it is 18.6% now)
- completions per cycle fall below **8.0** across a whole day

## 6. How to measure it

```bash
cd /mnt/workspace/LaclauGPT-Data-Analysis
.venv/bin/python tools/ai26_prompt_budget_audit.py \
  --log /mnt/workspace/LaclauGPT-Private/runtime/ai26/analysis/ai26-laskin-analysis.log --days 7
```

`--json` gives the same data for a dashboard or a cron report. The tool is read-only and parses the
worker's own log lines; it does not query the store and does not change a single setting.

## 7. What this document does not decide

It does not decide that dropping `memory` is acceptable. It records that it is happening, prices the
three levers, and sets the thresholds at which the question must be asked again.
