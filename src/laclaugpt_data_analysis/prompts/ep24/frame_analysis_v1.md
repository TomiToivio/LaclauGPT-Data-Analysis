You are analysing one frame from a 2024 European Parliament election social-media video.

Frame: {frame_id}
Timestamp seconds: {timestamp_seconds}
Country/language context: {project_note}

Return a structured, literal observation before any interpretation.

1. Visible text and UI: transcribe legible words, handles, slogans, logos and platform/screen-recording indicators. Mark uncertain OCR/reading explicitly.
2. People and groups: describe only what is visually supportable. Do not infer identity, party, ideology, profession, nationality, motive or importance from appearance alone.
3. Objects and symbols: identify flags, logos, signs, posters, microphones, buildings and other salient objects only when visually supported.
4. Setting and activity: describe location type and visible action without inventing campaign context.
5. Framing/cinematography: record shot type, composition and edits descriptively. A close-up, colour palette or background is not by itself evidence of political importance, sentiment, populism or ideology.
6. Candidate political cues: list only cues directly visible in the frame and label them provisional. Do not perform final discourse or populism analysis at frame level.
7. Uncertainty: list anything that cannot be identified reliably.

Absence is a valid result. Do not fill missing political meaning with plausible context from the election, codebook or model knowledge.