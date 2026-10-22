# AI26 quality-review template for a bounded batch

Adapted from the EP24 reproducible review template (upstream #295) for AI26's own objects. Use it when
a merged change needs a human read of what the pipeline actually produced — not when you want to know
whether the code runs, which is what the tests and the contract verifier answer.

**Why a template at all.** "The suite is green" says the code does what its author described. It says
nothing about whether the analysis is any good. A review that is not sampled, not recorded and not
dated becomes an opinion; this one produces a table that a second person can re-run.

## 1. Sample

- Draw **20 records** from one completed analysis window (`run_id` + date range recorded).
- Stratify by **arena** and by **source kind** so one platform cannot dominate: at least two arenas and
  three source kinds, if the window contains them.
- Include deliberately awkward cases if present: a non-English record, a record with no media, a
  duplicate/replayed source, and the longest record in the window.
- Record the filter you used. A sample that cannot be re-drawn is not reproducible.

## 2. What to check, per record

Read the record and answer each line **yes / no / n-a**, with one short note when "no".

| # | Check | What "no" means |
| --- | --- | --- |
| 1 | Every quotation in the analysis appears in the source text | A quote that cannot be found is fabricated or paraphrased; the evidence gate should have marked it inexact |
| 2 | Character offsets point at the quoted text | Offsets are the audit trail; wrong offsets make verification impossible |
| 3 | Uncertainty and abstentions are present when the source is thin | Confident claims over a two-line post are the failure this catches |
| 4 | Sociotechnical imaginaries are **described, not invented** | "One speculative future" must not be reported as a stabilised imaginary |
| 5 | No ideological label is inferred from author, account or arena | Labels must come from articulated content |
| 6 | Collective subjects and frontiers are attributed to evidence, not to the model's prior | — |
| 7 | Status flags distinguish `not_applicable` from `failed` | A silent success is worse than a visible gap |
| 8 | Provenance present: source URL, native IDs, prompt and model version, prompt hash | Without it the output cannot be cited or reproduced |
| 9 | Steps 7/8 (if enabled) are visibly marked experimental | Their output must never read as a validated finding |
| 10 | Nothing in the record contradicts the source's own stance | The commonest real error is plausible-but-wrong |

## 3. Record

| record id | arena | kind | checks failed | note |
| --- | --- | --- | --- | --- |
| | | | | |

Totals: `___/20` clean · `___` with a minor defect · `___` with a substantive defect.

## 4. Disposition

- **Clean** — nothing to do.
- **Minor** (wording, missing uncertainty, cosmetic provenance) — note it; no re-run needed.
- **Substantive** (fabricated quote, wrong offsets, ideological label from an author, invented imaginary,
  missing status where a stage failed) — **stop and open an issue**. A substantive finding is a defect in
  the pipeline or the prompt, not a bad record, and it invalidates any count computed from that window.

**Do not fix a substantive finding by editing the record.** Find where the value came from: the prompt,
the postprocess mapping, the evidence gate, or the taxonomy vocabulary. Editing the output hides the
bug and leaves the count wrong.

## 5. When to run this

- After a change to a prompt, the codebook, the evidence gate or the taxonomy vocabulary.
- Before any number from a window is used in a paper or a claim.
- Monthly on a fixed sample for drift, even with no change — corpora change under a stable pipeline.

Record the reviewer, the date, the window, the deployed git SHA and the `config_revision` /
`codebook_revision` with the table. A review without the revision identifies nothing.
