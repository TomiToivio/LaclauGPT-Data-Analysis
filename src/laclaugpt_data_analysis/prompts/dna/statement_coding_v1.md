Code DNA-compatible statements from the current source.

Configuration:
- concept_mode: {concept_mode}
- require_binary_agreement: {require_binary_agreement}
- duplicate_policy: {duplicate_policy}

For each candidate statement:
1. Identify the actual speaker. A named person may have an organization only when affiliation is supported. An organization may speak institutionally without a named person.
2. Formulate one substantively meaningful, reusable concept or proposition. Use an existing codebook concept only when the evidence clearly maps to it. Otherwise create a provisional concept candidate when configuration permits.
3. Code agreement=true only for clear support/affirmation of the concept as formulated. Code agreement=false only for clear rejection/opposition.
4. If support/opposition is ambiguous, ironic, sarcastic, second-hand, quoted without endorsement, merely narrated by a reporter, or otherwise unsupported, set agreement=null and use agreement_status=ambiguous/not_applicable/abstain rather than forcing a binary value.
5. Copy evidence_text exactly from SOURCE_EVIDENCE. Supply zero-based start and stop character offsets into the source text when possible. stop is exclusive.
6. Keep person and organization distinct. Do not turn a mentioned actor into the speaker.
7. Preserve source-language evidence. Concept normalization may follow the project codebook/canonical language.
8. Preserve repeated source-level evidence by default. A deterministic duplicate key is computed downstream from document, actor, concept and agreement.
9. Never infer a DNA agreement value from LaclauGPT Us/Them/frontier/equivalence/antagonism labels.
10. Treat prior analysis, RAG and periodic context as context only, never as evidence that this source contains the statement.

Important edge cases to handle conservatively:
- reporter narration without an attributed position;
- a speaker quoting an opponent;
- unclear sarcasm or irony;
- person known but organization unknown;
- organization speaking without a named person;
- multilingual Finnish, Polish and English material;
- multiple distinct claims in one source;
- paraphrases that should map to the same stable concept only when semantic equivalence is well supported.

Return only the requested structured output.