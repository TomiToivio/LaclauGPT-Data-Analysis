[SOURCE URL]
{source_url}

[CURRENT SOURCE ITEM]
{source_text}

[CONTEXT: CODEBOOK CANDIDATES, NOT EVIDENCE]
{codebook_context}

[TASK]
Return explicit topics, sentiment observations, stance, floating/empty-signifier candidates, equivalence/difference chains, antagonisms and actor/entity relations only when supported by the current source item. Do not invent multimodal evidence for text-only records. Keep theoretical candidates provisional and report uncertainty or abstention when evidence is insufficient.\n\n[EVIDENCE RULE] Every value you store as `quote` must be a contiguous span copied verbatim from [CURRENT SOURCE ITEM] -- never a paraphrase, translation, description, summary or a stitched fragment of several passages. If no verbatim span supports an object, write `no verbatim evidence found` for it rather than inventing or paraphrasing a quotation. An abstention is always acceptable; a paraphrase presented as a quotation is not.
