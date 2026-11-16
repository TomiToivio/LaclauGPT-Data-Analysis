# AI26 review-data quality audit (issue #444)

## Current dependency (2026-11-16, rechecked)

Private PR [#69](https://github.com/TomiToivio/LaclauGPT-Private/pull/69)
has merged its exporter code, but a repository inspection found only
`analysis/ai26/exports/review/README.md`, not the live
`ai26_review.csv` and `MANIFEST.json`. Consequently **no row-level
scientific accuracy assessment, pipeline quality gain or evidence-based
codebook revision can yet be claimed**. The full snapshot under
`analysis/ai26_snapshot/` is a backup with separate inclusion rules,
not a replacement for the issue #68 review export.

**Updated GitHub state:** `analysis/ai26/exports/review/ai26_review.csv` and
`MANIFEST.json` are now tracked in the private repository, but the GitHub
connector returns Git LFS *pointer text*, not hydrated data. Historical issue
comments also describe an earlier `analysis/ai26/review/` export with
5,302 rows and a 100-record sample, but that location is not on current
`main`. Therefore previous counts are historical, not freshly validated.
On an authenticated checkout, run `git lfs pull` and validate the current
payload/manifest before evaluating any source interpretations. Never publish
private row-level data or credentials. The exporter can emit either full
`source_text` or the compact `text_excerpt` projection, depending on version;
the audit detects both. A 600-character excerpt is **insufficient for
asserting hallucinated quotations absent from the full source**.


## When the live export exists

On an authorized workstation/Laskin with both repositories available:

```bash
cd /path/to/LaclauGPT-Data-Analysis
python tools/ai26_review_export_audit.py \
  --input ../LaclauGPT-Private/analysis/ai26/exports/review/ai26_review.csv \
  --manifest ../LaclauGPT-Private/analysis/ai26/exports/review/MANIFEST.json \
  --report ../LaclauGPT-Private/analysis/ai26/exports/review/quality_aggregate.json \
  --private-sample ../LaclauGPT-Private/analysis/ai26/exports/review/quality_sample.csv \
  --seed 444 --per-stratum 3
python -m pytest -q tests/test_ai26_output_audit.py tests/test_ai26_review_export_audit_444.py
```

Keep both output files in the private repo and **review confidentiality before any
commit**. Never paste sample rows, URLs or quotations into a public issue/PR.
The JSON contains only aggregate counts, platform/arena buckets and missingness,
not a quality score. Check sparsity of small buckets before sharing aggregates.
The sample is deterministic, stratified by platform, arena and summary presence.
It does not claim representativeness of non-analyzed records; the sampling frame is
the exported analyzed population. Record the export digest and seed alongside
human annotations.

## Human coding protocol

1. Privately review full source evidence and summary/formation/signifier/imaginary
   outputs for each sampled item. Verify quoted evidence against source content.
   Distinguish missing source data, software defects, scientific coding disagreement
   and unsupported inferred claims.
2. Mark independent judgments for source fidelity and Phase 1 construct fit,
   including uncertain/abstained labels. Use a second reviewer where feasible.
   Do not treat model-produced interpretations as gold labels.
3. Freeze a held-out evaluation sample before making repairs. Trace recurring
   defects to the responsible analysis stage and write a regression fixture first.
4. Propose codebook changes only for evidenced recurring failures. Public
   conceptual changes belong in `codebooks/public/`, private overlays in
   `LaclauGPT-Private`. Preserve approved Phase 1 concepts, version revisions,
   and re-freeze the effective codebook before any approved runtime rollout.
5. Re-run the fixed sample under identical model/runtime settings where possible;
   compare evidence fidelity, valid outputs and reviewer agreement. Record
   regressions and unresolved interpretive differences separately.

### Verified code-level correction

The existing `ai26_output_audit.py` incorrectly treated records with only
formations, signifiers, discourses or imaginaries as `complete_without_findings`:
these Phase 1 analysis fields were missing from its `FINDING_FIELDS` tuple.
This branch corrects that **audit detector**, with synthetic regressions. This
is not evidence that the underlying AI26 model was inaccurate, and does not
alter the analytical methodology, prompts or codebooks.

## Deferred until data is available

- Accurate per-field missingness and source-grounded hallucination/error rates.
- Any attribution of observed errors to specific model prompts or codebooks.
- Codebook changes justified by repeatedly observed misclassifications.
- Before/after measured accuracy improvements and Laskin production validation.

The existing canonical JSONL audit is `tools/ai26_output_audit.py`; use it for
evidence offsets, relation references, provenance and stale plugin outputs
when richer records are available. The new CSV auditor does not duplicate
those semantic checks.

## Measuring a change: `tools/ai26_review_delta.py`

The exporter above profiles and samples one export. The before/after step in #444 needs the other
direction — the same records, two versions — so that tool stays the only profiler and this one does
one job:

```bash
python tools/ai26_review_delta.py --before old.csv --after new.csv --json delta.json
```

It is paired on `record_id` and reports, per Phase 1 concept, how many records **gained** a value, how
many **lost** one, and how many summaries changed. Gains and regressions are separate columns because a
net figure hides a regression behind two improvements; `--fail-on-regression` makes that a gate.

Two things it deliberately reports instead of smoothing over:

- **Population changes.** Comparing the 5,302-row export with the 3,632-row one gives 3,632 shared ids
  and **1,670 only-before**: the newer export keeps only the newest analysis result per `source_url`.
  That is a change of population, not a defect, and it is counted rather than folded into a percentage.
- **Absent columns.** If a concept has no column in the older file, the row says `absent` rather than
  `0`, because "not measured" and "measured as zero" are different facts — the distinction the whole
  audit rests on.

Coverage is all it measures. An empty cell becoming filled says the pipeline produced something, never
that the interpretation is right; the source-grounded reading pass is still a human task with the
audit sample as its denominator.
