Produce a researcher-readable political analysis of one EP24 video from the evidence bundle.

Project context: {project_note}
Evidence bundle:
{evidence_text}

Use the original-language transcript as primary verbal evidence and translation only as an aid. Integrate metadata, ASR, OCR and timestamped visual observations, but keep modality disagreements visible.

Return these sections:
1. Evidence synopsis: what happens in the video, with source/timestamp references where available.
2. Political/non-political classification and content type. Abstain when evidence is insufficient.
3. Difficult language and translation notes, preserving original expressions.
4. Political topics and explicit claims, each tied to evidence.
5. Entities/actors and their roles. Prefer codebook canonical names only when the source mention supports the match.
6. Sentiment/affect with explicit target. Do not infer sentiment from colour palette, camera distance or other neutral visual style alone.
7. Grievances, demands, promises and projected futures when explicitly or strongly supported.
8. Multimodal contradictions or uncertainties.
9. Concise human-readable summary.

Do not invent political context merely because the corpus concerns an election. A plausible campaign interpretation without source evidence must be recorded as not_evidenced, not as a finding.