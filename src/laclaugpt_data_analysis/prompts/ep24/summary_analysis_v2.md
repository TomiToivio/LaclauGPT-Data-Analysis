Produce a researcher-readable political analysis of one EP24 video from the full multimodal evidence bundle.

Project context: {project_note}

This EP24 v2 summary must preserve ALL analytical obligations of the legacy `puhti_summary.py` prompt while using the current staged, evidence-first pipeline. Use original-language transcript as primary verbal evidence; translation is an aid. Integrate metadata, ASR, OCR, timestamped visual observations and prior deterministic/NLP stage outputs, and keep modality disagreements visible.

Return ALL of these sections:

1. Narrative Construction
- Reconstruct the sequence of events/actions in the video.
- Identify events/actions that shape the video's narrative.
- Cite timestamps/evidence identifiers when available.

2. Political Classification
- Classify political vs non-political, with abstention when evidence is insufficient.
- If political, provide a content type such as candidate personal video, campaign speech, protest, political meme, election advertisement, media coverage, interview, commentary or other evidence-supported category.

3. Difficult Language
- Identify words/phrases in transcript or metadata that are difficult to translate, ambiguous, idiomatic, memetic, dialectal, code-switched or politically charged.
- Preserve original-language wording and explain uncertainty rather than silently normalising it.

4. Key Political Topics
- Identify major political topics and describe how each is presented.
- Tie every topic to source evidence; do not infer a topic merely from election context or codebook membership.

5. Political Entities
- List politicians, parties, movements, organisations and other political actors actually supported by the evidence.
- Describe their role in the video.
- Prefer codebook canonical names only when the source mention supports the match.

6. Sentiment Analysis
- Identify positive, negative or neutral sentiment/affect and its explicit target.
- Justify classifications with transcript, audio, OCR or visual evidence.
- Do not infer sentiment from colour palette, shot distance or neutral visual style alone.

7. Political Populism, legacy-compatible preliminary observations
- Preserve the legacy request to inspect empty signifiers, chains of equivalence and people-versus-elite/frontier cues.
- At this summary stage these are ONLY evidence-linked candidates for the later dedicated Laclau/Mouffe/Palonen pass.
- Do not complete a populist structure when Us, demands, equivalential links, frontier and affects are not supported. `not_evidenced` is valid.

8. Social Contract
- Preserve the legacy social-contract category.
- Identify explicit or strongly supported claims about reciprocal obligations, rights, duties, legitimacy, representation, authority, public provision or expectations between citizens and political institutions.
- Do not invent an implicit social contract from generic political content.

9. Grievance Politics
- Identify expressed grievances, perceived injustices, blocked demands or conflicts.
- Describe any evidence-supported connection to mobilisation, conflict or political action without predicting effects not present in the source.

10. Claims, Demands, Promises and Futures
- Extract explicit claims, demands, promises, desirable futures and feared futures when present.
- Distinguish speaker/uploader position from quoted or reported speech.

11. Multimodal Evidence Audit
- Note agreement or contradiction among metadata, ASR, OCR, frames, translation and previous analysis steps.
- Record weak/ambiguous evidence and missing modalities.

12. Researcher Summary
- Give a concise human-readable synthesis that does not exceed the evidence.

General rules:
- Context, codebooks, RAG and researcher notes guide retrieval/normalisation but are not source evidence.
- Preserve quoted/reported speech attribution.
- A plausible campaign interpretation without source support must be marked `not_evidenced`.
- Keep preliminary sociology/multimodal description separate from the later dedicated Laclau/Mouffe/Palonen, DNA and Critical AI Studies stages.