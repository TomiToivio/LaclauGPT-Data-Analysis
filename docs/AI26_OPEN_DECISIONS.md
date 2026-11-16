# AI26: the open decisions, with the numbers that make them decidable

Status: **decision memo, 2026-11-16.** Nothing in this document has been applied. Each section names the
issue that carries the decision, the measurement behind it, the options, and a mechanical success
criterion — so that after the decision, "did it work?" is a query, not an opinion.

All numbers were re-measured against the live canonical store on 2026-11-16 (`ai26__analysis_results`,
newest analysis per source, **3,634 sources**), not copied from the issue where the defect was reported.
Aggregates only.

## Why these are one decision and not seven

`themes`, `discourses` and `them` are declared in `AnalysisSection` and exported to reviewers; none is
produced. `#458` (citations), `#460` (evidence gate) and `#454` (label vocabulary) all change what the
instrument emits. Applying them one at a time produces a corpus that is half-coded under one rule and half
under another, which is exactly the condition `#444` was opened to end. The audit's own recommendation is to
change the instrument **once**, then evaluate on the fixed 72-row reference sample.

## The measurement, in one place

| field | populated | share of 3,634 |
| --- | ---: | ---: |
| `us` | 2,948 | 81.1 % |
| `them` | **0** | 0 % |
| `formations` | 3,455 | 95.1 % |
| `signifiers` | 2,754 | 75.8 % |
| `nodal_points` | 3,442 | 94.7 % |
| `antagonisms` | 2,212 | 60.9 % |
| `floating_signifiers` | 2,482 | 68.3 % |
| `imaginaries` | 2,633 | 72.5 % |
| `themes` | **0** | 0 % |
| `discourses` | **0** | 0 % |
| `equivalences` | **0** | 0 % |
| `codebook_refs` | **0** | 0 % |
| `model_runs[].codebook_revision` | **0** | 0 % ← fixed for new runs by #462 |

Source-text quality of the same population (classifier in `text_quality.py`, #449):

| kind | sources | share |
| --- | ---: | ---: |
| prose | 1,955 | 53.8 % |
| sparse_prose | 629 | 17.3 % |
| markup_heavy | 768 | 21.1 % |
| code | 256 | 7.0 % |
| empty | 27 | 0.7 % |

**957 records whose text is unusable were nevertheless coded.** The `web` platform is the extreme case:
256 of 260 records are script/style dumps.

Coding is not evidence-gated: records with **zero source text** receive a formation label **96.3 %** of the
time — as often as 3,000-character documents (#460).

Citations: **38.3 %** of 91,426 quotations cannot be located in the record's own text even after stripping
markup and all non-alphanumerics; for English-only citations, 36.4 % (#458, #457).

## D1 — `discourses` has no producer (#450)

Options: (a) produce it — a stage returns discourse objects and `postprocess` assigns them, as with
`formations`; (b) retire it — remove from `AnalysisSection`, the export and the prompt, so no reviewer sees
a permanently empty column.

Recommended for decision: **(b) retire now, revisit in Phase 2.** `discourses` would duplicate
`formations` + `antagonisms` + `signifiers` in this pipeline, and nothing in the current stage set computes
a discourse as a bounded object. Producing it is a new construct, not a bug fix.

Success criterion: the export has no column that is empty in 100 % of rows except by explicit declaration.

## D2 — `them` and the us/them pair (#452)

`us` is written from `discourse.collective_subjects`; `them` is written nowhere, while `research_record.py`
and `rdf.py` both export the pair. A consumer sees one pole of an antagonistic relation.

Options: (a) split `collective_subjects` into us/them by a named criterion; (b) derive `them` from the
antagonism relations (`target_ref` of an antagonism whose `source_ref` is in `us`); (c) retire `them` and
stop exporting a pair.

Recommended for decision: **(b) with a named criterion and a guard** — but only if Tomi accepts that
"the antagonistic pole of a coded antagonism" is the definition of `them`. It is the only derivation the
corpus already supports; (a) requires a criterion the codebook does not yet state, and (c) discards a
field the theory needs.

**Decided (2026-11-16): (c), retire the pair — with the opposed pole kept where the source states it.**
`phase1_v1.yaml` declares `collective_subjects` and no `them`, so the codebook-derived answer is the
collective subject, not a two-pole formula. The pipeline now writes `analysis.collective_subjects`; `us`
becomes a documented read-only legacy alias (lifted into `collective_subjects` on load) and `them` is not
derived or exported for Phase 1. Nothing is lost: an opposed pole the source states is already an
`antagonism` relation with a `target_ref`.

Success criterion: `them` populated iff a record has an antagonism whose source is in `us`; both empty
otherwise; no record with `them` and empty `us`.

## D3 — `themes` asked for, dropped by the schema (#453)

`prompts/laclau/document_analysis_v1.md:11` asks the model for "topics/themes"; `DiscourseProposal` has no
`themes` field, so a theme cannot survive validation, and `postprocess` never assigns `analysis.themes`.

Options: (a) wire `themes` through proposal → postprocess and name the Phase 1 concept it operationalises;
(b) remove it from the prompt and from `AnalysisSection`.

Recommended for decision: **(b) remove from the prompt, keep the field reserved** until a decision names
what a theme is that `topics` (already populated) does not capture. Leaving the prompt asking for output
the schema discards spends tokens on text that is thrown away.

Success criterion: the prompt requests only fields the schema can store; a test enumerates the two sets
and compares them (the companion guard in this PR covers the canonical side).

## D4 — analyses without source text, and coding without evidence (#451, #460)

27 sources have no stored text; 957 have unusable text; 96.3 % of the zero-text stratum carries a formation.

Options: (a) **abstain** — `status = no_evidence`, no coded fields, the record stays as collected-only;
(b) **analyse metadata deliberately** — keep the analysis but mark provenance as metadata-derived so
downstream metrics can separate it; (c) leave as is.

Recommended for decision: **(a) for `empty` and `code`, (b) only if a study explicitly wants
metadata-only coding.** The gate must be measured in both directions: unusable strata fall, 3,000+
character prose does not.

Success criterion (mechanical, on the fixed 72-row sample): coded fields without a resolving evidence span
→ ~0; formation coverage in the 0–150 character strata falls to what the text supports; coverage for
3,000+ character prose is unchanged.

## D5 — formation label vocabulary (#454)

1,221 distinct formation labels: **106 token-shaped** labels covering 2,532 rows, **1,115 prose-shaped**
labels covering 1,406 rows. One 11-character label covers **899 rows (24.7 %)**.

Options: (a) closed, versioned vocabulary in the codebook, prose formulations demoted to `description`;
(b) keep free text and normalise downstream; (c) leave as is.

Recommended for decision: **(a)**, plus explicit inclusion/exclusion criteria for the dominant label —
at 24.7 % it may be a genuine dominant formation or a catch-all, and only stated criteria can tell.

Success criterion: distinct labels per 1,000 rows falls by an order of magnitude; the dominant label's
share is explained by its criteria; no label is free text.

## D6 — citations: require verbatim quotation (#458)

35.2 % of sampled citations are paraphrase (audit §7); 38.3 % are unlocatable under permissive matching.

Options: (a) prompt requires verbatim spans and abstains otherwise, plus one correction round when
`locate_quote` fails; (b) keep paraphrase and record `evidence_kind` per span; (c) leave as is.

Recommended for decision: **(a) with (b) as the recorded fallback** — the machine can already tell which
spans resolve, so the honest minimum is that a stored citation always says which kind it is.

Success criterion: verbatim share of citations on a fixed sample; the number must be reported from the
same measurement that produced the baseline, not from a new instrument.

## What this memo does not do

It does not rank the decisions by importance for Tomi's paper, and it does not implement any of them. Each
section is written so that the *implementation* is mechanical once the choice is made — which is the only
part an agent should be doing without the author.
