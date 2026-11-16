# AI26 review-export audit and sampling (#444)

The review dataset (`LaclauGPT-Private: analysis/ai26/review/`) is the surface a human reads to judge
whether the model's interpretation holds. Before any accuracy judgement can mean anything, two
questions about the dataset itself have to be answered: **is anything missing that the pipeline
produced** (an export defect), and **is anything missing because the pipeline produced nothing** (a
pipeline or collection defect). They look identical in a spreadsheet — an empty cell — and have
different owners.

`tools/ai26_review_audit.py` answers both, and draws the audit sample.

```bash
python tools/ai26_review_audit.py --input review.csv --profile
python tools/ai26_review_audit.py --input review.csv --sample 100 --seed 444 --out sample.csv
python tools/ai26_review_audit.py --compare before.csv after.csv --json compare.json
```

It reads a CSV, writes nothing else, and never contacts the store. Its console output contains
counts, column names and status values only: **no URL, title, summary, transcript or model label**.
The sample carries record ids and stratum facts; `--include-source-url` exists for a file that stays
private.

## Terms this page uses precisely

| term | meaning here |
| --- | --- |
| **export defect** | the pipeline produced something, the export did not carry it. Owner: the exporter. |
| **pipeline gap** | the canonical schema declares a field the pipeline never fills. Owner: Data-Analysis. |
| **collection gap** | the analysed item has no stored source text, so no fidelity check is possible. Owner: Data-Collection. |
| **coverage** | the share of rows in which a field has a value. It is never an accuracy figure. |
| **regression** | a record that had a value before a change and has none after. |

## Profile of the export as received (5,302 rows, one per analysed item)

- identity: 5,302 rows, 5,302 unique `record_id`, 0 duplicates, 0 blank `source_url`;
- 21 columns as contracted, UTF-8 clean, multiline summaries intact;
- `analysis_status` and `analysis_version` are single-valued (`analyzed`, one model version), so no
  model-to-model comparison is possible from this dataset;
- 82 rows carry **no stored source text** — these cannot be audited for fidelity at all;
- 230 rows carry **no coded formation**;
- 316 summary values are repeated exactly (max 8 occurrences), 4840 distinct — a template-answer
  signal that a per-row reading would not surface;
- language is blank on 274 rows; titles are blank on 4,591 — the second is expected on
  microblogging platforms, the first is a metadata gap.

## What the profile exposed

| finding | evidence | owner |
| --- | --- | --- |
| **Antagonisms were exported blank although the pipeline produced 3,407 of them (64.3%)** | canonical `antagonisms` are `Relation` objects (`relation_type`, `source_ref`, `target_ref`), and the exporter's generic label helper looked for `label`/`name`/`term`, found none, and emitted an empty string | exporter (fixed) |
| **Phase 1 concepts missing from the dataset entirely** | `imaginaries` 73.3%, `us` 83.3%, `floating_signifiers` 70.1% of canonical records have them; the export had no such columns, so a reviewer could not audit them | exporter (fixed) |
| **`discourse_status` repeated `analysis_status`** | both read `analysis.status`, so the column could never disagree with the column beside it and carried no information | exporter (fixed: derived, and labelled as derived) |
| **`themes`, `discourses`, `them`, `classifications`, `topic_assignments` are 0/5,302** | declared in the canonical schema, never assigned by the postprocess stage | Data-Analysis gap, filed as a follow-up |
| **`codebook_refs` is empty on all 5,302 records** | the record cannot be tied to the codebook that produced it, which blocks the "which codebook is actually used" question in #444 step 4 | Data-Analysis gap, filed as a follow-up |
| **82 rows without source text, concentrated on one platform** | mastodon: 122 of 203 rows have text; every other platform is ~100% | Collection gap, filed against Data-Collection |
| **The exporter's own tests tested an API that no longer existed** | all four committed tests failed with `AttributeError` (`document_row`, `choose_latest`, `export`) | exporter tests (rewritten) |

## Before/after, on the same 5,302 record ids

The exporter fix changes what the dataset *carries*, not what the model said. Paired comparison:

| concept | before | after | gained | lost |
| --- | --- | --- | --- | --- |
| antagonisms | 0 | **3,407** | 3,407 | 0 |
| imaginaries | — (no column) | **3,886** | 3,886 | 0 |
| us | — (no column) | **4,418** | 4,418 | 0 |
| floating_signifiers | — (no column) | **3,716** | 3,716 | 0 |
| formations | 5,072 | 5,072 | 0 | 0 |
| signifiers | 4,099 | 4,099 | 0 | 0 |
| nodal_points | 5,052 | 5,052 | 0 | 0 |
| summaries | 5,302 | 5,302 | 0 | 0 |

Zero regressions and zero summary changes: the projection changed, the analysis did not. **This is
not an accuracy gain and must never be reported as one.** It is the removal of a blind spot that
made 3,407 antagonisms and four Phase 1 concept families unreviewable.

## The sample

`--sample 100 --seed 444` over strata `platform × has-text × has-formation`, allocation by largest
remainder with a floor of one per non-empty stratum (13 strata, all represented). Selection is by
`sha256(seed:record_id)`, so the same seed draws the same records even if the export is regenerated
in a different row order — a property the tests pin.

The floor exists because proportionality alone drops exactly the cases an audit is for: an 8-row
no-formation stratum and a 2-row stratum receive zero rows under pure proportional allocation.

## What this tool cannot do

It cannot tell you whether an interpretation is *right*. That needs a human reading the source text
against the model's summary and coding, and the issue says so explicitly ("do not invent numeric
gains"). The tool produces the population facts, the sample, and the coverage delta; the accuracy
review is a reading pass with the sample as its denominator.
