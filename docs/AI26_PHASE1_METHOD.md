# Reading an AI26 record as social-science evidence

A model can locate a passage and propose how its speaker gives meaning to AI. A researcher must decide whether the passage supports that reading, whose position it expresses, and how far the inference travels. This guide traces those decisions through the Python package. The six operations come from §3.4 of [Tomi Toivio’s Phase 1 paper, *LaclauGPT: Ideological contestation over AI*](https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md). They describe research work, so their numbering differs from software stage numbers.

## Six operations in the repository

| Paper operation | Implementation and observable output | Researcher’s check |
| --- | --- | --- |
| 1. Prepare and preserve sources | Implemented in [preprocess_record](../src/laclaugpt_data_analysis/stages/preprocess.py). A canonical record retains its source URL. Optional preprocessing appends derived ASR, OCR, frames or translations and records a preservation flag. | Inspect the retained representation and its origin. The flag alone cannot establish that a complete original was captured. |
| 2. Describe the document | Implemented in [summarize_record](../src/laclaugpt_data_analysis/stages/summary.py). The model writes a descriptive summary to `human_readable.summary` and records its run in `analysis.model_runs`. | Return to the passage before coding. A summary can erase quotation marks or merge the journalist’s voice with a source’s voice. |
| 3. Propose theoretical codes | Implemented as proposals in [discourse_analysis](../src/laclaugpt_data_analysis/stages/laclau.py). The stage reads source text, records the stage result and retains model-run metadata. The [prompt envelope](../src/laclaugpt_data_analysis/context_envelope.py) distinguishes source material, prior analysis and retrieved context. | Identify the relation and its textual warrant. A codebook entry can suggest a question; only the source can supply evidence for this case. |
| 4. Resolve identities while preserving contextual meanings | Partial. [merge_codebooks](../src/laclaugpt_data_analysis/codebooks.py) layers entries by kind and normalized label and fingerprints the effective version. The [optional statement coder](../src/laclaugpt_data_analysis/dna_statement_coding.py) can preserve original concept wording alongside a concept ID. | Check aliases and contextual use. A later layer can override an earlier entry. The merged book alone does not supply the history of rejected matches envisioned in §3.4. |
| 5. Compare across the corpus | Partial. [build_periodic_summary](../src/laclaugpt_data_analysis/periodic_summary.py) aggregates records over a time window and scope. Its counts and evidence references help locate recurring candidates. | Examine comparable records and contrary cases. More mentions may reflect collection coverage or repeated publication. Establishing hegemony requires contextual evidence that a project has succeeded in making its account more widely authoritative. |
| 6. Review and interpret | Partial. [provisional_ai_annotation and import_dats_human_correction](../src/laclaugpt_data_analysis/dats_review.py) represent a model proposal and a separately attributable human review event. | Retrieve the original passage, document a decision and explain the revision. These exchange helpers do not demonstrate that an annotation has been independently reviewed. |

The [human-owned Laclaudian step](../laclaugpt/step_05_laclau.py) describes the intended operation but currently raises `NotImplementedError`. The package functions above provide inspectable implementations. An optional analysis path only contributes outputs when enabled.

## What counts as evidence for a theoretical code?

In Laclau and Mouffe’s account, articulation is a relation that changes what its elements mean together. Ask what a speaker makes AI *mean* by connecting it to prosperity, labour or national survival. In §3.1, **nodal** describes a term that organizes other meanings within a discourse. **Floating** requires evidence of competing projects struggling over its meaning. **Tendentially empty** requires showing how a particular signifier comes to stand for a wider chain of heterogeneous demands. Ambiguity in a single quotation cannot settle any of these readings (Laclau & Mouffe, 2001; Laclau, 1996, 2005).

Use Palonen’s Formula of Populism when the material supports a collective subject, a political frontier and affective investment in that identification. Record the passages that support each inference. An opponent’s appearance or a negative sentiment score alone leaves the assessment open (Palonen, 2025; paper §3.1).

Critical AI Studies directs attention to who controls technology, whose interests it serves and whose work or resources it depends on (Lindgren, 2023). Provisional formation labels guide comparison while allowing overlap, uncertainty and unforeseen positions (§2). A sociotechnical imaginary entails a collectively sustained vision of a desirable social order. A promise in one speech gives a lead; evidence of circulation, institutional commitments or repeated public enactment would strengthen a collective reading (Jasanoff, 2015).

## Worked example: who made the claim?

Suppose a journalist writes this synthetic passage in `record.content.text`:

> The minister said, “AI will bring prosperity to every region.” The reporter asked who would fund the programme.

1. Retain the article’s `source_url` and the original passage. A descriptive summary might say the article reports a ministerial promise and a question about funding.
2. In the optional DNA coder, a plausible candidate has `person.label` set to “the minister”, `concept.label` set to “AI as a source of regional prosperity”, and `evidence_text` set to “AI will bring prosperity to every region.” The conversion checks the quote against `record.content.text` and writes `actor_name`, `concept_label`, `source_url`, and `evidence.quote`, with character offsets when located. The comparison field is fixed in this function; the span alone does not identify the source field. For a different representation, trace its origin separately. [Statement conversion and exact-span matching](../src/laclaugpt_data_analysis/dna_statement_coding.py)
3. An exact match gives the statement provisional status. Read the attribution outside the quotation: the minister makes the promise, while the reporter asks about financing. The passage supports a candidate articulation of AI with prosperity. It leaves the journalist’s endorsement, a national consensus and a populist frontier unestablished. Where stance is ambiguous the coder can retain an unknown stance and abstention. [Statement coding cases](../tests/test_dna_statement_coding_cases.py)
4. If a model attributed the promise to the journalist, a reviewer could submit a DATS event with `target_id` identifying the reviewed annotation, `reviewer`, `reviewed_at`, `decision="REVISED"` and a `note` explaining the attribution; `corrections` carries the field edits for that target. Preserve the initial proposal. The DATS importer accepts an explicit target ID; it does not automatically convert this DNA statement into a DATS annotation or apply the review to the source record. [Review adapter test](../tests/test_interoperability_graphs_and_review.py)

## Comparing cases and validating interpretations

For the elite, grassroots, and parliamentary/electoral arenas (§4.1), record the sampling frame, period, source genre, language and missing coverage before comparing the prevalence of a code. An institutional press release and a grassroots post may use the same term with different stakes. Examine the original language when translation could alter a frontier or collective identification. Keep private sources and identifiable review material within the study’s access controls (§4.4).

The [verbatim-evidence tests](../tests/test_issue458_verbatim_evidence.py) exercise normalized matching, paraphrase rejection and abstention in the stages evidence policy. The optional DNA coder above has its own literal span check. [Periodic-summary tests](../tests/test_periodic_summary.py) exercise aggregation, and the review adapter test checks that a correction names its target and preserves a decision. These tests establish software properties. The paper’s proposed validation (§§4.2–4.3) also requires researchers to inspect cases, examine disagreement and document interpretive limits. No performance or inter-coder agreement estimate follows from a passing test (Lindgren, 2020; Grimmer et al., 2022).

## References

- Grimmer, J., Roberts, M. E., & Stewart, B. M. (2022). *Text as Data: A New Framework for Machine Learning and the Social Sciences*. Princeton University Press.
- Jasanoff, S. (2015). Future imperfect: Science, technology, and the imaginations of modernity. In S. Jasanoff & S.-H. Kim (Eds.), *Dreamscapes of Modernity*, pp. 1–33. University of Chicago Press. [DOI](https://doi.org/10.7208/chicago/9780226276663.001.0001)
- Laclau, E. (1996). *Emancipation(s)*. Verso.
- Laclau, E. (2005). *On Populist Reason*. Verso.
- Laclau, E., & Mouffe, C. (2001). *Hegemony and Socialist Strategy: Towards a Radical Democratic Politics* (2nd ed.). Verso.
- Lindgren, S. (2020). *Data Theory: Interpretive Sociology and Computational Methods*. Polity.
- Lindgren, S. (2023). Introducing critical studies of artificial intelligence. In S. Lindgren (Ed.), *Handbook of Critical Studies of Artificial Intelligence*, pp. 1–19. Edward Elgar. [DOI](https://doi.org/10.4337/9781803928562)
- Palonen, E. (2025). *The Birth and Death of Liberal Democracy in Hungary: The Populist Logic of Polarisation as Hegemony*. Helsinki University Press. [DOI](https://doi.org/10.33134/pro-et-contra-4)
