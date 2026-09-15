# EP2024 multimodal migration map

This document records the functional audit of the archived `TomiToivio/LaclauGPT-Multimodal-Analysis` pipeline and maps reusable behavior into the canonical `laclaugpt_data_analysis` package.

The legacy repository is treated as a reference implementation, not as the target architecture. No EP2024 research data, participant media, transcripts, OCR output, researcher annotations, real CSC paths, target lists, or private codebooks are copied here.

## Migration decisions

| Legacy source | Behavior | Classification | Canonical home / decision |
|---|---|---|---|
| `puhti_preprocess.py` | up to six frames sampled every 30 s | REIMPLEMENT_CLEANLY | `multimodal.frames.sample_timestamps`; deterministic policy, backend-neutral |
| `puhti_preprocess.py` | Whisper transcription | MIGRATE | `multimodal.adapters.AsrProvider`; concrete Whisper implementation remains optional/lazy |
| `puhti_preprocess.py` | EasyOCR extraction | MIGRATE | `multimodal.adapters.OcrProvider`; concrete OCR implementation remains optional/lazy |
| `puhti_preprocess.py` | cached/idempotent preprocessing | ALREADY_IMPLEMENTED / REIMPLEMENT_CLEANLY | canonical storage/resume layer should key by document/evidence IDs; no private SQLite layout copied |
| `puhti_preprocess.py` | hard-coded EP2024 languages and Allas paths | PRIVATE_OR_STUDY_SPECIFIC_DO_NOT_COPY | runtime configuration belongs outside reusable library code |
| `puhti_frame.py` | frame-level vision analysis | MIGRATE | `multimodal.adapters.VisionProvider` + `VisualObservation` |
| `puhti_frame.py` | frame timestamp association | MIGRATE | explicit `timestamp_seconds`, `frame_id`, and evidence IDs |
| `puhti_frame.py` | EP2024-specific visual prompt and fixed Ollama model | PRIVATE_OR_STUDY_SPECIFIC_DO_NOT_COPY | conceptual categories may live in public codebooks; provider/model selection belongs to canonical LLM layer from issue #2 |
| `puhti_summary.py` | transcript + OCR + frame + metadata fusion | MIGRATE | `MultimodalEvidenceBundle` + `build_evidence_text` |
| `puhti_summary.py` | researcher-readable per-video synthesis | MIGRATE | `researcher_summary`; canonical structured record remains primary |
| `puhti_summary.py` | election-specific summary prompt | REIMPLEMENT_CLEANLY | analysis/codebook layer from issue #2, not multimodal plumbing |
| `puhti_postprocess.py` | flattening and deterministic tabular export | MIGRATE | `exporters.write_multimodal_csv` / `write_multimodal_jsonl` |
| `puhti_postprocess.py` | topics/entities/sentiment extraction via Ollama | ALREADY_IMPLEMENTED / REIMPLEMENT_CLEANLY | canonical structured analysis backends/codebooks, not a duplicate multimodal subsystem |
| `puhti_populism.py` | typed Formula-of-Populism result | MIGRATE INTO #2 CANONICAL THEORY PIPELINE | retain Laclau/Palonen concepts in canonical codebooks/models rather than a separate legacy runner |
| `puhti_populism.py` | model names, SQLite files, EP2024 filenames | OBSOLETE / STUDY_SPECIFIC | not copied |

## Modern multimodal flow

```text
media metadata
  + ASR transcript segments
  + sampled frame references
  + OCR observations
  + visual observations
        ↓
MultimodalEvidenceBundle
        ↓
deterministic evidence rendering
        ↓
canonical analysis/codebook/LLM pipeline from issue #2
        ↓
structured canonical result
        ↓
researcher-readable summary + JSONL/CSV export
```

Every derived observation carries an evidence identifier and timestamp/frame reference so downstream interpretation can cite its source evidence. Large media blobs are never embedded in canonical JSON.

## Local and HPC execution

The core package performs no model loading, network access, browser access, GPU initialization, or filesystem writes at import time. Concrete Whisper, OCR, OpenCV, vision-LLM, Ollama, or remote providers should be optional adapters. Local paths, scratch roots, object-store URIs, model names, and batch sizes must come from runtime configuration.

CSC/Puhti/Roihu support should therefore be implemented as thin deployment examples or runners around the same library APIs. Public examples must use placeholders and must not contain usernames, project allocations, private endpoints, or real study paths.

## Historical methodology retained

The useful historical pattern is preserved: combine speech, visible text, sampled visual evidence, and source metadata before interpretation; retain per-frame timing; tolerate missing modalities; produce both structured output and a human-readable researcher view; and make expensive stages resumable.

The old fixed six-column CSV representation, import-time model loading, hard-coded EP2024 paths/languages, one-database-per-stage architecture, and fixed model prompts are deliberately not preserved.

## Privacy

Tests use invented text and metadata only. Do not add real EP2024 videos, screenshots, frames, transcripts, OCR observations, participant/account data, study target lists, or researcher annotations to this public repository.
