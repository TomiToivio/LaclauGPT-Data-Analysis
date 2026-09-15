# Four-layer research record in Data Analysis

Analysis must enrich the Collection record without losing source fidelity or intermediate processing evidence.

## Required behavior

- Preserve `raw_capture`, source metadata/content, source identity and Collection provenance unchanged.
- Keep Whisper/ASR, language detection, translations, OCR, sampled frames and frame/multimodal descriptions in the explicit `intermediate` section.
- Append stage/model outputs with provenance rather than silently discarding prior stage results.
- Keep the full current structured LaclauGPT analysis under `analysis`.
- Regenerate `human_readable` from the complete current record after analysis.
- Regenerate the wide legacy researcher projection after analysis. Historical values survive when no newer canonical result replaces them.

## Default researcher outputs

`write_research_bundle()` emits three synchronized representations from the same canonical record objects:

1. canonical JSONL;
2. wide legacy-compatible `*_researchers.csv`;
3. one complete Markdown report per record.

The incremental real-time JSONL runner also refreshes the researcher CSV and report directory after each pass.

The researcher CSV contains deterministic JSON columns for all nested sections plus familiar fields such as `whisper_transcript`, `whisper_language`, `whisper_translated`, `ocr_1...ocr_6`, `frame_1...frame_6`, `summary_analysis`, source/ID/date aliases, entities/topics/sentiments, Formula-of-Populism aliases, historical topic-model/classifier columns when imported, `raw_ref`, `raw_payload_json`, and human-readable summary/report columns.

MongoDB and SQLite store the complete canonical record, not only the wide dataframe projection. S3/Allas may hold large referenced artifacts. Redis remains control/cache/coordination infrastructure.
