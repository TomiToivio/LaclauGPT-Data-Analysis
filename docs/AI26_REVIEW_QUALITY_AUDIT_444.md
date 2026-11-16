# AI26 review-data quality audit (issue #444)

## Current evidence gate (2026-11-16)

The **current private main branch tracks** `analysis/ai26/exports/review/ai26_review.csv`, `MANIFEST.json`, and `README.md`. The GitHub connector returns **Git LFS pointer text**, not hydrated research data. At inspection the CSV pointer declared SHA-256 `b93713a5ab577499e1995a15874e16dec099aac79786fcb3d864c5ea671863cd` and 50,721,584 bytes; the manifest was also an LFS pointer. These are *tracked-object metadata*, **not** an independent checksum or row-level validation of the actual working-copy payload.

Previous authenticated Laskin audit comments on [#444](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/issues/444) report 5,302 analysis documents collapsed to 3,632 distinct reviewed items, 2,210 filled antagonism fields, and 27 items without source text, and describe verified manifest checks. Treat those as **reported results from that environment**, not independent measurements from this connector. Earlier 5,302-row exports counted analysis versions rather than unique items and must not be mixed with the corrected denominator.

The corrected projection and export changes were merged in [Private #73](https://github.com/TomiToivio/LaclauGPT-Private/pull/73); older comments about missing exports and alternate `analysis/ai26/review/` paths are historical. The snapshot `analysis/ai26_snapshot/` is a backup with separate inclusion rules, not a substitute for the current review export.

**Remaining gate:** hydrate the CSV and manifest in an authenticated, authorized workstation/Laskin environment, verify their content SHA-256, schema, row/URL uniqueness and source-join integrity, and inspect full source evidence for the qualitative sample. Git LFS pointers alone cannot establish source-grounded coding accuracy.

## Run the audit on hydrated private data

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
The merged review-auditor fix corrects that **audit detector**, with synthetic regressions. This
is not evidence that the underlying AI26 model was inaccurate, and does not
alter the analytical methodology, prompts or codebooks.

## Deferred until hydrated data and human review are available

- Independent verification of the corrected export's field missingness and source-grounded hallucination/error rates in the current environment.
- Any attribution of observed errors to specific model prompts or codebooks.
- Codebook changes justified by repeatedly observed misclassifications.
- Before/after measured accuracy improvements and Laskin production validation.

The existing canonical JSONL audit is `tools/ai26_output_audit.py`; use it for
evidence offsets, relation references, provenance and stale plugin outputs
when richer records are available. The new CSV auditor does not duplicate
those semantic checks.
