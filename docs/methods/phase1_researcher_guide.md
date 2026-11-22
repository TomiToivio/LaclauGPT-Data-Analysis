# Phase 1 researcher guide: from source to reviewed interpretation

**Authority:** [Phase 1 paper, §§2–4](https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md). This guide describes the *current code*, not evidence that the proposed method is validated. Research-paper phases are **not** software branch versions. See also [AI26 reference case](../AI26_REFERENCE_CASE.md), [canonical record](../CANONICAL_RECORD.md), [Critical AI Studies implementation](critical_ai_studies.md), [pipeline](../DATA_ANALYSIS_PIPELINE.md), and issues [#523](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/issues/523) and [#303](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/issues/303).

The unit of analysis in paper §3.4 is a source document or context-preserving segment, **not** an automatically true ideological label. Follow one record's `source_url`, `source.author`, `source.language`, `source.created_at`, `content.text`, `intermediate.stage_outputs`, `evidence`, `analysis`, and `review`. A record's `source.author` identifies the source author, *not necessarily the speaker of each embedded quotation*. `source.raw_metadata` can preserve additional collection-specific attribution; it is not a verified quotation-speaker contract.

## Six research operations in §3.4 and their code locations

| Paper operation | Current implementation / code links | Input → output and researcher checkpoint | Status |
| --- | --- | --- | --- |
| 1. Preserve sources | [canonical.py](../../src/laclaugpt_data_analysis/canonical.py), [preprocess.py](../../src/laclaugpt_data_analysis/stages/preprocess.py), [runner.py](../../src/laclaugpt_data_analysis/stages/runner.py) | `source_url`, source metadata, text/derived media → source-preserving `CanonicalRecord`, `intermediate` and preprocessing stage audit. Inspect missing/incorrect original text and collection attribution before interpretation. | **Implemented in Analysis for incoming canonical records**; upstream collection completeness must be independently audited. |
| 2. Describe document | [summary.py](../../src/laclaugpt_data_analysis/stages/summary.py), [runner.py](../../src/laclaugpt_data_analysis/stages/runner.py) | Source material / modality summary → descriptive `intermediate.stage_outputs` and summary. Reviewer must distinguish document author, quoted actor, irony, opposition and hypothetical claims; automatic speaker resolution cannot be assumed. | **Partial** for paper-level attributed-position requirements. |
| 3. Propose codes | [laclau.py](../../src/laclaugpt_data_analysis/stages/laclau.py), [proposals.py](../../src/laclaugpt_data_analysis/stages/proposals.py), [evidence.py](../../src/laclaugpt_data_analysis/stages/evidence.py), [postprocess.py](../../src/laclaugpt_data_analysis/stages/postprocess.py) | Prior description, prompts/codebook and source → provisional `analysis.signifiers`, `nodal_points`, `floating_signifiers`, `empty_signifier_candidates`, `equivalence_chains`, `antagonisms`, `imaginaries`, `collective_subjects`, `uncertainty`, `abstentions`, each as applicable. Inspect `evidence_ids` and counter-readings. | **Implemented as proposals**, not validated interpretation. |
| 4. Reconcile identity/codebook | [codebooks.py](../../src/laclaugpt_data_analysis/codebooks.py), [formation_vocabulary.py](../../src/laclaugpt_data_analysis/formation_vocabulary.py), [runner.py](../../src/laclaugpt_data_analysis/stages/runner.py) | Supplied codebook entries/aliases and provenance → prompt context and revision fingerprint. A string alias is not proof of an equivalent political meaning; check original wording and author context. | **Partial**: full human adjudication history, rejected semantic merges and superseded identity workflows in §3.4 must not be assumed. |
| 5. Compare corpus | [exporters.py](../../src/laclaugpt_data_analysis/exporters.py), [claims.py](../../src/laclaugpt_data_analysis/claims.py), [formation_vocabulary.py](../../src/laclaugpt_data_analysis/formation_vocabulary.py) | Linked source/claims/actor and `arena`/time/language → exportable candidate comparisons. Countable categories are aggregation aids, **not** evidence of hegemony or equivalential chains. | **Partial**: joins and projections exist; corpus-level inference and sampling validity remain researcher work. |
| 6. Review and interpret | [canonical.py](../../src/laclaugpt_data_analysis/canonical.py), [claims.py](../../src/laclaugpt_data_analysis/claims.py), [evidence_gate.py](../../src/laclaugpt_data_analysis/evidence_gate.py) | `Evidence.metadata.exact`, proposed codes, `review.status`/reviewer/notes; claim adapter also carries `validation_status`, `reviewed_by`, `reviewed_at`, `correction_note`. Researcher checks speaker/context, rejects/revises/accepts. | **Partial**: schema permits review and export, but a completed, independently adjudicated evaluation is **not demonstrated** here. |

The named source fields are defined by [`SourceSection`, `ContentSection`, `Evidence`, `AnalysisSection`, and `ReviewSection`](../../src/laclaugpt_data_analysis/canonical.py). The distinct DNA-compatible claim representation is [`claim_from_canonical`](../../src/laclaugpt_data_analysis/claims.py). Do **not** confuse claim-adapter fields (`actor_id`, `evidence_quote`, `validation_status`) with core `CanonicalRecord` fields: these are different representations.

### Exact-span checking is necessary, never sufficient

[`locate_quote`](../../src/laclaugpt_data_analysis/stages/evidence.py) tries direct matching, whitespace/case normalisation and ordered ellipsis segments, returning offsets in original `content.text`. [`evidence_ids`](../../src/laclaugpt_data_analysis/stages/evidence.py) records `Evidence.quote`, `start_offset`, `end_offset`, `metadata.exact` and `metadata.review_status="PROVISIONAL"`. Nonmatches remain visible for auditing; a deliberate `no verbatim evidence found` abstention is not promoted to a citation. The optional [evidence gate](../../src/laclaugpt_data_analysis/evidence_gate.py) can withhold unsupported coded objects; **it is off by default**. Neither a direct match nor an elided-span match verifies speaker identity, quotation boundaries, endorsement, irony, rhetorical function or a theoretical code. Elision may cover intervening contradictory content. Always inspect the surrounding original material and source field. See paper §3.4 and Grimmer, Roberts & Stewart (2022).

The analysis prompt is selected and versioned through [`laclau.py`](../../src/laclaugpt_data_analysis/stages/laclau.py), [prompt map](../../src/laclaugpt_data_analysis/stages/prompt_map.py) and [prompt library](../../src/laclaugpt_data_analysis/prompt_library.py). Codebook entries are contextual cues rather than observations; [runner](../../src/laclaugpt_data_analysis/stages/runner.py) fingerprints supplied entries when a runtime revision is missing. Human review must check that no prior proposal was recycled as verified source material (Lindgren 2020; paper §§3.2–3.4). Do not edit the locked prompts, numbered steps, codebooks or schemas for this guide.

## Theoretical questions the researcher must answer (paper §§2–3)

- **Nodal point:** does `AI` organise relationships among multiple signifiers and demands *within a particular discourse*? Show relational passages, not merely frequent word use.
- **Floating signifier:** do *competing projects* attach different meanings to `AI`? Compare articulated contrasts across identifiable speakers/sources, not just dictionary polysemy.
- **Tendentially empty signifier:** is `AI` invested with representing a *broader equivalential project or imagined collective fullness*, beyond a specific technical object? Show demands being linked and wider political identification. Vague, broad or popular usage alone does not establish this.
- **Equivalence, difference, antagonism:** similarity is not equivalence; disagreement and negative sentiment are not an antagonistic frontier. A chain needs evidence of demands joined relationally through a shared obstacle; difference can preserve distinct demands (Laclau & Mouffe 2001; Laclau 2005).
- **Palonen's Formula of Populism:** assess only when there is evidence of *constituted Us*, a *frontier*, and their *affective investments*. It is interpretive, **not** `us_count + them_count` or sentiment arithmetic. If no frontier, constitutive identification or affect is evidenced, leave `analysis.formula_of_populism` unassessed rather than claiming every political conflict is populist (Palonen 2025; paper §3.1).
- **Imaginaries:** a single actor predicting AI-led prosperity offers a *candidate future vision*, not proof of a collectively held or institutionally stabilised sociotechnical imaginary. Check repetition across independent sources and institutional enactment (Jasanoff 2015; paper §2.2).
- **Critical AI Studies:** `ideologies shaping AI`, `ideologies reproduced through AI`, and `ideological contestation over AI` answer different questions about sociotechnical power. The [optional critical AI module](../../src/laclaugpt_data_analysis/critical_ai.py) does not automatically validate a Laclaudian reading (Lindgren 2023; paper §2.1).
- **Formation labels:** accelerationism, doomerism, left-wing accelerationism, AI safety, AI critical and anti-AI are provisional retrieval/aggregation anchors, *not* an exhaustive ontology or assumptions based on who authored the text. Leave uncertain, overlapping or nonmatching cases unresolved. See [AI26 reference](../AI26_REFERENCE_CASE.md) and [formation vocabulary](../../src/laclaugpt_data_analysis/formation_vocabulary.py).

## Synthetic worked example: minister quoted by a journalist

**Invented source, not a corpus observation.** Suppose `source_url="https://example.org/synthetic/minister-interview"`, `source.source_type="article"`, `source.author="Example Reporter"`, `source.language="en"`, and `content.text='The minister said, "AI will secure our national prosperity." The reporter noted that labour unions disputed this claim.'`. Preserve the full article, the enclosing speaker-attribution clause, original publication date in `source.created_at`, and any separately documented provenance under `source.raw_metadata`.

1. The model may propose a *minister-attributed* prosperity articulation and the exact quote `"AI will secure our national prosperity."`. [`evidence_ids`](../../src/laclaugpt_data_analysis/stages/evidence.py) adds an `Evidence` with `source_url`, `quote`, `start_offset`, `end_offset`, `metadata.exact=True`, and a **provisional** review status if the span resolves in `content.text`. Link a provisional `analysis.signifiers` or `analysis.imaginaries` `DiscourseObject` via `evidence_ids`, plus uncertainty about speaker/meaning.
2. The *source author* is the journalist; the *speaker of the quoted assertion* is the minister. A quote match proves only presence of text in this record. It cannot establish the reporter endorses it, the minister has realised prosperity, or a shared national imaginary. Record the reporter's reported labour-union disagreement as a possible counter-reading, **not automatically** a Laclaudian antagonism.
3. Where actor-level statement coding is used, [`claim_from_canonical`](../../src/laclaugpt_data_analysis/claims.py) consumes a **separate proposed claim** with `actor_id="minister-synthetic"`, `actor_name="Example Minister"`, `concept_id="ai-national-prosperity"`, `evidence_quote="AI will secure our national prosperity."`, `evidence_start`, `evidence_end`, `stance="support"`, `validation_status="provisional"`, `abstained=False`. The offsets must be obtained from the actual source string, not copied from this paragraph. It binds to `record.source_url`; source field and speaker attribution still need independent inspection. For the reporter's *own* position, **abstain** unless a separate attributed passage supports it.
4. A human checks the full sentence, quotation marks, reporter attribution and alternative reading. At the record level a reviewer may set `review.status="ACCEPTED"`, `"REVISED"` or `"REJECTED"` with `review.reviewer`, `review.reviewed_at` and `review.note`; an individual `DiscourseObject.review_status` is separately provisional by default. For a claim adapter the fields are `validation_status`, `reviewed_by`, `reviewed_at`, `correction_note`. **No review update is performed by this guide.**

**Current gaps:** `Evidence` does **not** have a required `source_field` or `speaker_id`; `evidence_ids` matches only `record.content.text` and does not establish quote-level speaker boundaries. `SourceSection.author` stores the document author rather than the minister; `source.raw_metadata` can carry a documented source field, but this alone does not solve attribution. `claim_from_canonical` accepts an externally supplied `actor_id` and validates offsets, but does not infer or independently verify the speaker. Any per-claim reviewer decision needs a separate claim-review workflow. These are limitations, **not** instructions to silently add fields.

## Comparative inference and validation: paper §4

Compare elites, grassroots mobilisation and parliamentary/electoral politics only after documenting each arena's **sampling frame, inclusion criteria, sources, observation window, language, collection method, and missingness**. The same actor may occupy multiple arenas; `arena` is sampling provenance, not evidence for formation classification. Cross-language equivalence, circulation of a signifier between arenas, and institutional uptake require contextual checks rather than word-count charts. Source concentration, duplicated content, access restrictions, translations, model changes and uneven representation may confound comparisons. Frequency can aid retrieval, **not establish hegemony** (Laclau & Mouffe 2001; Jasanoff 2015).

The paper **proposes** independently double-coded held-out evaluation samples, human–human versus model–human agreement, speaker-attribution/span accuracy, class-wise metrics, abstention/coverage analysis, disagreement retention, multilingual and arena breakdowns when cell sizes permit, and robustness to other models and prompts without formation seeds. None of these procedures should be reported as **completed validation** merely because a unit test or an evaluation template exists. Tests of [quote matching](../../src/laclaugpt_data_analysis/stages/evidence.py), [schema validation](../../src/laclaugpt_data_analysis/canonical.py) and [claim adapter](../../src/laclaugpt_data_analysis/claims.py) can demonstrate bounded *mechanical* properties only; their existence is not evidence of interpretive validity. See [review quality audit](../AI26_REVIEW_QUALITY_AUDIT_444.md) for documented implementation-level concerns. A genuine evaluation needs a dated corpus/annotation manifest, sampling plan, independent coded gold/reference material, and published results (Grimmer, Roberts & Stewart 2022; paper §4.2).


### Which test earns each status claim

The table above says *implemented* or *partial*; this says what makes that true, so a reader can check the
claim instead of trusting it. A passing test here establishes a **mechanical** property, never interpretive
validity.

| property | test |
| --- | --- |
| a quotation is located in the retained source, or kept as non-exact | `tests/test_evidence_span_strictness.py`, `tests/test_evidence_source_grounding.py`, `tests/test_issue458_verbatim_evidence.py` |
| an abstention replaces coding when there is no source evidence | `tests/test_issue_460_evidence_gate.py`, `tests/test_issue451_no_source_evidence.py` |
| every coded object defaults to `PROVISIONAL`, and a declared field has a producer | `tests/test_field_contract.py`, `tests/test_canonical_contract.py` |
| codebook entries validate and carry a revision fingerprint | `tests/test_codebook_context_selection.py`, `tests/test_phase1_codebook_context.py` |
| the collection handoff and canonical contracts stay stable | `tests/test_analysis_contracts.py`, `tests/test_collection_handoff_contract.py` |


## Where the current code and the paper's design differ

Each row is a concrete path, so a reader can confirm the mismatch rather than take it on trust.

1. **Five declared analysis fields are never produced:** `embeddings`, `entity_mentions`, `representations`,
   `us`, `them`, `topic_assignments` are registered as such in `src/laclaugpt_data_analysis/field_contract.py`,
   which fails a test if a field is added without a producer or registered without a stated reason. Two are
   *decisions*, not lapses: `us`/`them` were replaced by `collective_subjects` + `frontier` (#452). The
   `discourses` field was retired outright (#484) and is migrated out of stored records on load
   (`canonical.py`), so an older record shows it removed rather than empty. Of the five, only
   `entity_mentions` bears directly on operation 2 — it is the field that would have made speaker/mention
   attribution queryable.
2. **Codebook identity is not recorded per analysis in the current corpus:** `analysis.codebook_refs` is empty
   on every record and `model_runs[].codebook_revision` is unset (#459). Operation 4 can be audited for new
   runs only.
3. **Identity resolution has no review history:** `codebooks.py` validates, fingerprints and merges, but
   there is no accepted/rejected record of identity decisions, which §3.4 operation 4 asks for explicitly.
4. **Review is a status, not a record of reasoning:** `ReviewStatus` on an object says what was decided;
   nothing stores why, and a `REVISED` object is not linked to the disagreement that produced it.
5. **No corpus-level analysis view:** operation 5 is served by measurement tools
   (`tools/ai26_ready_frame_audit.py`, `tools/ai26_corpus_diagnostics.py`) and exports, not by an implemented
   analysis layer. Organising candidate relations by actor, time, language and arena remains researcher work.

## Supplementary distinctions from the methodological audit

### 3.2 Nodal points, floating signifiers, empty signifiers

These are three **functions**, not three kinds of word (Laclau and Mouffe, 2001; Laclau, 1996,
2005). The same signifier can be a nodal point in one discourse and contested elsewhere.

| Function | What it does | What the evidence must show | What is *not* enough |
| --- | --- | --- | --- |
| **Nodal point** | partially fixes meaning by organising other signifiers | other signifiers are related *through* it, and their meaning shifts in that relation | it is frequent, or prominent |
| **Floating signifier** | is subject to competing attempts at fixation across projects | two or more projects attach different meanings to it | it is vague, or has many senses |
| **Tendentially empty signifier** | comes to stand for a wider equivalential chain and an absent fullness | the chain is present, and the signifier represents the project beyond its particular reference | breadth or vacuity (§3.1: "mere breadth, vagueness, or multiple meanings establishes none of these functions") |

Frequency can guide retrieval; it cannot establish any of the three. The code emits
`nodal_points`, `floating_signifiers` and `empty_signifier_candidates`; treating them as findings
without the corpus-level comparison in operation 5 is a category error.

### 3.3 Equivalence, difference, antagonism

Equivalence links heterogeneous demands through a shared relation to an obstacle without erasing
their difference. **Difference is not the opposite side of a frontier** — it may describe demands
accommodated within an institutional order. Antagonism is a constitutive limit: an identity
organised against what is represented as preventing its fulfilment. Policy disagreement, criticism
and negative sentiment are therefore *not* evidence of an antagonistic frontier (paper §3.1).

### 3.4 Affective investment is not sentiment

`sentiment` (summary stage) identifies evaluative language. **Affective investment** is the
attachment through which a signifier, demand or collective identity acquires political force; it
must be read in relation to its object and the surrounding articulation (§3.1). The discourse
prompt therefore asks the model to distinguish generic sentiment from affective investment, and
`affects` is a separate output field. A sentiment score is not an affect code.

### 3.5 Sociotechnical imaginaries

An imaginary connects a vision of technological development to a desirable social order
(Jasanoff, 2015; Richter et al., 2023). Document-level analysis can identify **candidate** future
visions — diagnoses of the present, desired outcomes, feared alternatives, authorised agents of
change. It cannot establish that an imaginary is *collectively held and institutionally
stabilised*; that requires operation 5 (§2.2). A prediction or a personal hope is not an
imaginary, and a feared future is examined against the desirable order it threatens rather than
being equated with one.

### 3.6 Palonen's Formula of Populism: when it applies

$\text{Populism} = \text{Us}^{\text{Affects}_{1}} + \text{Frontier}^{\text{Affects}_{2}}$

(Palonen, 2025.) The formula is an **interpretive device, not a numerical model** (§3.1). It is
`formula_of_populism` in the `palonen` capability, implemented inside the shared discourse stage.

- **Applies** when the document constructs a collective subject ("Us") *and* a constitutive
  antagonistic frontier, each with evidenced affective investment.
- **Abstain** when one of the two is missing, when the frontier is merely an opponent or a policy
  disagreement, or when affects are asserted rather than evidenced. Finding an in-group and an
  opponent *initiates* an assessment; it does not establish populism. Anti-elite language alone is
  explicitly insufficient — the same rule is written into the discourse prompt.
- Affects carry **no fixed polarity** in advance; neither side of the formula is "negative".

A document may support an articulation or an imaginary while supporting no populism assessment at
all. `formula_of_populism` being absent is a valid, informative outcome.


## References

- Laclau, E., & Mouffe, C. (2001). *Hegemony and Socialist Strategy* (2nd ed.). Verso.
- Laclau, E. (1996). *Emancipation(s)*. Verso; Laclau, E. (2005). *On Populist Reason*. Verso.
- Palonen, E. (2025). *The Birth and Death of Liberal Democracy in Hungary*. Helsinki University Press. https://doi.org/10.33134/pro-et-contra-4
- Jasanoff, S. (2015). “Future Imperfect.” In *Dreamscapes of Modernity*, pp. 1–33. https://doi.org/10.7208/chicago/9780226276663.001.0001
- Lindgren, S. (2020). *Data Theory*. Polity; Lindgren, S. (2023). “Introducing Critical Studies of Artificial Intelligence.” https://doi.org/10.4337/9781803928562
- Grimmer, J., Roberts, M. E., & Stewart, B. M. (2022). *Text as Data*. Princeton University Press.
