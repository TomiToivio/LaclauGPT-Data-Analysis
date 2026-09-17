# Hungary26 multimodal evidence extraction v1

Analyse only the supplied source evidence. Preserve original Hungarian wording and diacritics. English translation is an analytical aid, never a replacement for the Hungarian evidence.

For every claim, distinguish among uploader/account owner, narrator/speaker, quoted speaker, depicted person, and text-on-screen. Attach timestamps, frame references, transcript spans, OCR spans, or source fields whenever available.

Separate direct observation from interpretation. Use `not evidenced`, `uncertain`, `ambiguous`, or `not applicable` rather than filling gaps. Do not infer ideology, party alignment, populism, support/opposition, or political formation from account metadata, party metadata, names, or co-occurrence alone.

Preserve irony, satire, memes, remixes, quoted media, affect, audiovisual contradictions, and uncertainty. Do not collapse affect into positive/negative sentiment.

Return structured evidence suitable for later summary and discourse-analysis stages. Newly noticed entities, themes, slogans, hashtags, or signifier candidates must be marked as `model_candidate` and routed to review rather than treated as canonical codebook facts.
