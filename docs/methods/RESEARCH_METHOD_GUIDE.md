# Research method guide — from one record to a reviewed claim

> **Who this is for:** a researcher who has one AI26 record in front of them and wants to know *where the
> software keeps an observation*, *where a model proposes a theoretical interpretation*, and *what evidence a
> human needs in order to accept, revise or reject it*.
>
> **Authority for theory and method:** Tomi Toivio, *LaclauGPT: Ideological contestation over AI*, Phase 1
> paper — [§2 concepts](https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md),
> [§3.4 the six-stage workflow](https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md),
> [§4 research design, validation, ethics](https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md).
> This guide does not replace the paper. It tells you which line of code implements which sentence of it, and
> where the two disagree.

## How to read this guide

Three layers are kept apart throughout, because collapsing them is the main way a computational discourse
analysis turns into a claim nobody can check.

| Layer | What it is | Where it lives |
| --- | --- | --- |
| **Observation** | A retained source, its provenance, and verbatim spans that mechanically resolve inside it | `canonical.py`, `stages/evidence.py` |
| **Proposal** | A model's *candidate* theoretical reading, with excerpts, uncertainty and abstention | `pipeline.py`, `stages/laclau.py`, `claims.py` |
| **Judgement** | A human accept / revise / reject decision, with a note and corrections | `canonical.py` `review`, `dats_review.py` |

A proposal is not a finding. `DiscourseObject.review_status` defaults to **`PROVISIONAL`** for exactly this
reason, and the repository's own README labels all model output as preliminary until verified.

## 1. The implementation the paper's workflow runs on

AI26 is implemented as a **declared stage registry**, not as prose. The single source of truth is
`src/laclaugpt_data_analysis/stages/registry.json` (format `laclaugpt.ai26.stage_registry`), and
`ai26.py` exposes it without a model call:

```bash
python -m laclaugpt_data_analysis.ai26 --help
```

Nine canonical stages — `handoff`, `preprocess`, `frame`, `video`, `summary`, `laclau`, `postprocess`,
`evidence`, `graph` — plus phase-2 stages `dna` and `sna`. Stage implementations live in
`src/laclaugpt_data_analysis/stages/`; prompts are packaged under
`src/laclaugpt_data_analysis/prompts/` (`laclau/discourse_analysis_v3.md` is the current discourse prompt;
`dna/statement_coding_v1.md` the statement-coding prompt).

**This registry is not the paper's six-stage workflow.** It is the *software* pipeline that carries the
workflow's work; the mapping is in §3 and the divergences in §9.

## 2. Vocabulary you need before reading code

The paper (§2) fixes the concepts; the implementation is careful to keep them as **provisional
descriptions**, not facts.

- **Articulation** — a practice establishing a relation between elements such that their identity changes
  (Laclau & Mouffe 2001). In code: a proposed relation between discourse objects, always evidence-linked.
- **Discourse** — a structured totality resulting from articulation. In code: never stored as a single
  object; it is the reviewed sum of relations, which is why the pipeline refuses to emit "the discourse".
- **Hegemony** — the partial fixation of meaning around nodal points. Not a scalar; a claim that needs
  contextual evidence (§4.2), never a frequency.
- **Nodal / floating / empty signifier** — the three roles the code can propose
  (`analysis.nodal_points`, `analysis.floating_signifiers`, `analysis.empty_signifier_candidates`).
- **Formation vocabulary** — the *only* place where an ideology-like label is normalised:
  `formation_vocabulary.py`, versioned `ai26-formations-2026-11-22`, six labels plus `other`/`unknown`
  fallbacks, all `PROVISIONAL`, and explicitly barred from asserting a person's ideology.
- **Critical AI Studies** — a required interpretive lens on AI discourse (Lindgren 2023), implemented as an
  *optional*, evidence-first stage: `critical_ai.py`, prompt under `prompts/critical_ai/`. See
  [`critical_ai_studies.md`](critical_ai_studies.md).
- **Sociotechnical imaginaries** — Jasanoff's (2015) shared visions of technological futures; in code these
  are `analysis.imaginaries`, proposals that need corroborating context, not a keyword list.

## 3. The six operations of §3.4, mapped to code

Statuses are **implemented** (code + test), **partial** (real but incomplete), or **proposed** (design only).
Every "implemented" claim cites the file it rests on.

| # | §3.4 operation | Where it happens | Input evidence | Output | Review point | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Prepare and preserve sources** | `canonical.py` (`CanonicalRecord`: `source_url`, `source`, `content`, `raw_capture`, `provenance`); ingestion stages `handoff`/`preprocess`/`frame`/`video` | Collected artefacts; OCR/ASR/translation kept as *separate representations* (`content.transcripts`, `.ocr`, `.frames`, `.translated_text`) | A canonical record with stable `source_url` and provenance chain | Provenance completeness; derived representation stays identifiable | **implemented** (`canonical.py`, `tests/test_canonical*.py`) |
| 2 | **Describe the document** | `stages/summary.py`, `stages/frame.py`, `framing.py`; descriptive pre-analysis feeding `laclau` | `content.text` and representations | Summary, topics, speakers, frames — descriptive, not theoretical | Whether a quoted position is distinguished from the author's own | **partial** — no dedicated "quoted vs asserted" field; see §9 M1 |
| 3 | **Propose theoretical codes** | `stages/laclau.py` (+ `pipeline.py` for object construction), `claims.py`, prompts `laclau/discourse_analysis_v3.md` | Descriptive pre-analysis + context + codebook | `DiscourseObject` / `Relation` proposals with `evidence_ids`, `confidence`, `uncertainty`, `review_status=PROVISIONAL`; abstention via `abstained=True` (`claims.py`) | Which excerpt supports which label; is abstention recorded rather than guessed | **implemented** (`pipeline.py`, `claims.py`, `tests/test_claims*.py`) |
| 4 | **Resolve identities without erasing meanings** | `codebooks.py` (`load_codebook`, `merge_codebooks`, `select_codebooks`, `seed_memory`, `entries_fingerprint`) | Recurring names/expressions from stage 3 | Versioned codebook entries; aliases; proposed merges | New entries and merges stay provisional until reviewed; rejected matches retained | **partial** — merge and versioning implemented; the *history of human decisions* is carried in the codebook/`review` sections but is not a first-class audit table (§9 M2) |
| 5 | **Compare across the corpus** | `derived_structures.py` (`project_network_relations`, `project_timeline_events`, `project_locations`), `discourse_network/`, phase-2 `dna`/`sna` | Reviewed codes across records | Projections by actor, time, language, arena | Repetition informs retrieval, never validates a theoretical code | **partial** — projections and DNA/SNA exist; arena is a record attribute (`source.country`/platform), not a first-class analytic dimension (§9 M3) |
| 6 | **Review and interpret** | `canonical.py` `ReviewSection` (`status`, `reviewer`, `reviewed_at`, `note`, `corrections`, `flags`, `rerun_requests`); `dats_review.py` (`provisional_ai_annotation`, `import_dats_human_correction`); `exporters.py` (`write_research_bundle`) | Proposals + source | Accept / revise / reject decisions, exported bundles | Every proposal must be revisitable back to the span | **implemented** (record-level); **proposed** as a per-object audit trail (§9 M2) |

### The mechanical check and the interpretive one

`stages/evidence.py:34 locate_quote(source_text, quote)` decides whether a quotation **occurs** in the
retained representation. A hit stores `start_offset`/`end_offset` and `Evidence.metadata["exact"] = True`; a
miss is stored anyway with `exact=False`, because "the model quoted this and it is not in the source" is
itself a finding.

`evidence_gate.py` consumes that flag: an object survives only if at least one of its `evidence_ids` resolves
to `exact: True`; otherwise the label is dropped into `analysis.uncertainty`, where a reader can see what was
proposed and not supported. It is **off by default** (`LACLAUGPT_AI26_REQUIRE_EVIDENCE`), and `dry_run=True`
computes what it *would* drop without altering the record.

> **The limit that matters:** a matching quotation establishes **textual presence only**. It does not
> establish who is speaking, whether the speaker endorses the statement, or whether the statement is
> evidence of a shared imaginary. Those remain interpretive acts, and the paper (§3.4) says so explicitly.

## 4. AI as nodal, floating or empty signifier

All three are *proposals*, and each requires different evidence.

| Reading | What it claims | Evidence required | Where it is coded |
| --- | --- | --- | --- |
| **Nodal point** | "AI" organises other signifiers; meanings are fixed around it | Several articulations converging on AI from the same discourse, each with located spans, plus evidence that other terms are defined *through* it | `analysis.nodal_points` |
| **Floating signifier** | "AI" carries competing meanings that different actors pull apart | At least two actors articulating AI differently, in comparable contexts | `analysis.floating_signifiers` — `pipeline.py` marks this kind `corpus_required` and stores `metadata.corpus_validation_required` |
| **Tendentially empty signifier** | "AI" is used precisely because it can mean anything to anyone | Evidence of *emptiness*: high generality, few concrete predicates, and actors with opposed politics adopting it without dispute | `analysis.empty_signifier_candidates` — also `corpus_required` |

The `corpus_required` rule in `pipeline.py` (`_candidate_objects`) applies to `floating_signifier`,
`empty_signifier` **and** `formation`, and is the implementation of a methodological point rather than a
technical shortcut: a single document cannot show a signifier to be *floating or empty*, nor an actor's
formation to be shared, because all three are claims about relations across a corpus. The flag is written
into each object as `metadata.corpus_validation_required`.

## 5. Palonen's Formula of Populism: when to apply it, when to abstain

The Formula of Populism (Palonen 2025) is a **conditional** component of theoretical coding — the paper calls
it conditional (§3.4), and the code follows that: it is not a global classifier.

**Apply it** when a document supplies all three, each with located evidence: a **collective subject**
("we/the people"), a **frontier** against an antagonistic other, and **affective investment** in the
signifier that unites them.

**Leave it unassessed** when any of the three is absent or only inferred. A document that supports an
articulation or an imaginary code **without** supporting a populism assessment should produce the former and
not the latter. Abstention is a valid, recorded outcome (`abstained=True` in `claims.py`), and it is
preferable to a forced triple.

## 6. Worked synthetic example

A journalist's article quotes a minister. All values below use the actual field names of `CanonicalRecord`.

### Observation

```jsonc
{
  "source_url": "https://example.invalid/article/minister-ai-2045",
  "source": { "platform": "news", "source_type": "article",
              "author": "A. Journalist", "language": "en",
              "collection_method": "rss" },
  "content": { "text": "… The minister said: \"Artificial intelligence is the engine of our national prosperity.\" …" }
}
```

`stages/evidence.py` locates the quoted span inside `content.text`, producing:

```jsonc
{ "evidence_id": "ev:1", "kind": "quote", "source_url": "…",
  "quote": "Artificial intelligence is the engine of our national prosperity.",
  "start_offset": 214, "end_offset": 283, "metadata": { "exact": true } }
```

### Proposal

```jsonc
{ "object_id": "signifier:0", "label": "artificial intelligence", "kind": "signifier",
  "evidence_ids": ["ev:1"], "confidence": 0.6,
  "uncertainty": "single attributed quotation; speaker is a minister, not the journalist",
  "review_status": "PROVISIONAL" }
```

### What this example does and does not establish

| Claim | Supported? | Why |
| --- | --- | --- |
| The phrase occurs in the article | **Yes**, mechanically — `exact: true` with offsets | `locate_quote` found it |
| The **minister** articulates AI with national prosperity | **Yes**, if `source.author` is kept distinct from the quoted speaker | The field that carries this is the quotation's own metadata plus the surrounding attribution, **not** `source.author` |
| The **journalist** endorses that articulation | **No** | Attribution is not endorsement; quotation is a reported speech act |
| A shared **national imaginary** exists | **No** | One article cannot carry a claim about a collective imaginary |
| Palonen's formula applies | **No** | No collective subject, frontier or affective investment is evidenced here |

### Where the implementation cannot yet represent the example

This is the honest part, and it is recorded in §9:

- there is **no dedicated field** for the quoted speaker of a span (M1) — attribution today lives in
  `content.text` and in prose around the quotation, so "who spoke" is recoverable by reading but not
  machine-checkable;
- the review decision is recorded at **record level** (`review.status`, `review.note`, `review.corrections`),
  not per `DiscourseObject` (M2) — so a reviewer can accept the record while rejecting one signifier, but
  the trace of that specific refusal is a free-text note.

### Following this example through the code

| Step | Code | What to look at |
| --- | --- | --- |
| Source retained | [`canonical.py`](../../src/laclaugpt_data_analysis/canonical.py) | `CanonicalRecord.source`, `.content`, `.provenance` |
| Quotation located | [`stages/evidence.py`](../../src/laclaugpt_data_analysis/stages/evidence.py) | `locate_quote()` → offsets + `metadata["exact"]` |
| Proposal built | [`pipeline.py`](../../src/laclaugpt_data_analysis/pipeline.py) | `_candidate_objects()` → `PROVISIONAL`, `evidence_ids` |
| Abstention honoured | [`claims.py`](../../src/laclaugpt_data_analysis/claims.py) | `claim_from_canonical()` |
| Unsupported labels dropped | [`evidence_gate.py`](../../src/laclaugpt_data_analysis/evidence_gate.py) | `apply_evidence_gate()` → `analysis.uncertainty` |
| Decision recorded | [`canonical.py`](../../src/laclaugpt_data_analysis/canonical.py), [`dats_review.py`](../../src/laclaugpt_data_analysis/dats_review.py) | `ReviewSection`, `import_dats_human_correction()` |
| Bundle exported | [`exporters.py`](../../src/laclaugpt_data_analysis/exporters.py) | `write_research_bundle()` |

### How the review decision is recorded

```jsonc
"review": { "status": "REVISED", "reviewer": "researcher-id",
            "reviewed_at": "2026-11-22T12:00:00Z",
            "note": "Quotation verified. Endorsement claim rejected: attribution only.",
            "corrections": { "signifier:0": { "confidence": null,
                                             "note": "keep as attributed articulation" } } }
```

`dats_review.import_dats_human_correction` and `exporters.write_research_bundle` carry these decisions into
the review exchange and the exported bundle.

## 7. Validation: what the tests actually verify

Mechanical properties have tests; interpretive ones do not, and cannot.

| Property | Verified by |
| --- | --- |
| Quote location, offsets, `exact` flag on hit and miss | `tests/test_canonical_pipeline_v2.py`, `tests/test_canonical_contract.py` |
| Evidence gate drops unsupported objects and records them in `analysis.uncertainty` | `tests/test_issue_460_evidence_gate.py` |
| Abstention is preserved rather than converted into a code | `tests/test_claims_adapter.py` |
| Formation labels normalise only known aliases; novel prose stays unresolved | `tests/test_issue_454_formation_vocabulary.py`, `tests/test_issue454_formation_aggregation.py` |
| Codebook merge is versioned and fingerprintable | `tests/test_issue_459_codebook_provenance.py`, `tests/test_codebook_context_selection.py` |
| Stage registry and prompts cannot drift from the declared map | `tests/test_issue_341_stage_registry.py` |

**Not validated by tests, and must not be claimed as such:** whether a code is theoretically apt, whether an
imaginary is shared, whether a frontier is real. Those are the researcher's judgement, informed by §4.2.

## 8. Comparing across arenas (§4.1)

The paper proposes comparison across **elites, grassroots mobilisation, and parliamentary/electoral
politics**. Any such comparison depends on four things the current implementation records but does not
harmonise:

| Dependency | Where it is recorded | Current limitation |
| --- | --- | --- |
| **Sampling** | `provenance`, `raw_capture`, collection method | Sampling frames are per-study; there is no cross-arena sampling object |
| **Language** | `source.language`, `content.language`, `translated_text` | Translation is retained as a representation, but comparability of translated codes is not evaluated |
| **Time** | `source.created_at`, `collected_at` | Present and reliable; periodisation is the researcher's choice |
| **Arena** | `source.platform`, `source.source_type` | Arena is inferred from platform/type conventions, not an explicit field |

**Proposed, not completed:** the arena comparison itself, and any claim of cross-arena validity. §4.2 makes
validation part of the method; this guide distinguishes that design from what has actually been evaluated.

## 9. Where current behaviour differs from the paper's design

Recorded rather than smoothed over, as the issue requires.

| ID | Paper says | Code does | Path | Consequence |
| --- | --- | --- | --- | --- |
| **M1** | Distinguish the author's position from quoted, rejected, hypothetical or ironic statements (§3.4 stage 2) | No dedicated field for a span's quoted speaker or epistemic status; the distinction is carried by prompt instruction and surrounding text | `canonical.py` (`Evidence`, `ContentSection`) | "Who said it" is readable but not machine-verifiable |
| **M2** | Codebook retains "the history of human decisions"; review accepts, revises or rejects **coding proposals** | Review is record-level (`ReviewSection`); per-object decisions live in free-text `corrections` | `canonical.py`, `dats_review.py` | One refused signifier is documentable but not queryable |
| **M3** | Organise candidate relations by actor, time, language **and arena** (§3.4 stage 5) | Time/actor/language are fields; arena is derived from `source.platform`/`source_type` | `derived_structures.py` | Arena comparisons are conventions, not a contract |
| **M4** | Populism assessment is conditional on collective subject + frontier + affect | No enforced precondition; the prompt asks, and abstention is available but not required | `prompts/laclau/discourse_analysis_v3.md`, `claims.py` | A forced triple is possible; `evidence_gate` only checks that *some* span resolves |
| **M5** | A run manifest records model digest, prompts, context, serving software | Model/prompt metadata is retained per record; a single study-level manifest object is not a first-class artefact here | `canonical.py` provenance, `freeze_run.py` | Reproducibility is per-record, not per-study |

None of these are bugs. Each is a place where the implementation is narrower than the design, and where a
researcher must not read more from the data than it can carry.

## 10. References

- Jasanoff, S. (2015). "Future Imperfect: Science, Technology, and the Imaginations of Modernity." In *Dreamscapes of Modernity*, pp. 1–33. University of Chicago Press. [DOI](https://doi.org/10.7208/chicago/9780226276663.001.0001)
- Laclau, E. (1996). *Emancipation(s)*. Verso.
- Laclau, E. (2005). *On Populist Reason*. Verso.
- Laclau, E., & Mouffe, C. (2001). *Hegemony and Socialist Strategy*, 2nd ed. Verso.
- Lindgren, S. (2020). *Data Theory: Interpretive Sociology and Computational Methods*. Polity.
- Lindgren, S. (2023). "Introducing Critical Studies of Artificial Intelligence." In *Handbook of Critical Studies of Artificial Intelligence*, pp. 1–19. [DOI](https://doi.org/10.4337/9781803928562)
- Grimmer, J., Roberts, M. E., & Stewart, B. M. (2022). *Text as Data: A New Framework for Machine Learning and the Social Sciences*. Princeton University Press.
- Palonen, E. (2025). *The Birth and Death of Liberal Democracy in Hungary: The Populist Logic of Polarisation as Hegemony*. Helsinki University Press. [DOI](https://doi.org/10.33134/pro-et-contra-4)

## Related documents

- [`critical_ai_studies.md`](critical_ai_studies.md) — the Critical AI Studies lens in full.
- [`dna_compatibility.md`](dna_compatibility.md) — Discourse Network Analysis compatibility.
- [`../AI26_OPEN_DECISIONS.md`](../AI26_OPEN_DECISIONS.md) — including D4, the evidence-gate decision.
