# Canonical analysis record

`LaclauGPT-Data-Analysis` implements the Analysis-side responsibilities of the project-wide contract in `TomiToivio/LaclauGPT/docs/CANONICAL_DATA_CONTRACT.md`.

The governing rule is simple: **Analysis enriches the source record. It does not replace its identity.** `source_url` (or an equivalent URI-like locator stored in that field) remains the stable source identity across Pydantic, JSON/JSONL, CSV/Pandas, SQLite, MongoDB and visualization handoff.

## Canonical shape

The implementation lives in `src/laclaugpt_data_analysis/canonical.py`:

```text
CanonicalRecord
├── schema_version
├── source_url
├── source_native_ids
├── source
├── content
│   ├── transcripts[]
│   ├── ocr[]
│   ├── frames[]
│   └── media_references[]
├── evidence[]
├── analysis
│   ├── representations[]
│   ├── entities[] / entity_mentions[]
│   ├── topics[] / topic_assignments[]
│   ├── classifications[] / embeddings[]
│   ├── formations[] / signifiers[] / nodal_points[]
│   ├── discourses[] / imaginaries[] / relations[]
│   ├── us[] / them[] / frontier[]
│   ├── affects[] / sentiments[]
│   ├── uncertainty[] / abstentions[]
│   ├── codebook_refs[] / memory_refs[]
│   └── model_runs[]
├── provenance[]
├── review
└── legacy
```

Large media remain external objects referenced by URI/path/checksum. Multimodal sections are optional; text-only records are valid first-class records.

## Backend rules

`src/laclaugpt_data_analysis/interchange.py` is the storage-neutral boundary.

- JSON/JSONL is the reference nested wire representation.
- CSV uses exactly two scalar identity/version columns plus deterministic JSON encoding for nested canonical sections. Python `repr` is never used for nested values.
- SQLite stores canonical JSON keyed by unique `source_url`; its row/database identity never replaces source identity.
- MongoDB stores the canonical document shape. `_id` is ignored when reconstructing the logical record.
- Pandas may consume/produce the CSV-compatible flat rows. `NaN` must be normalized at the adapter boundary.
- Parquet should use the same canonical dictionary or documented nested/JSON column encoding when an optional Parquet adapter is enabled later.

Time values are serialized as timezone-aware ISO 8601 values by Pydantic JSON mode. Optional values are `None`/`null`; optional collections default to empty lists.

## Collection compatibility

`from_collection_record()` maps the current public Data Collection `NormalizedRecord` to `CanonicalRecord` while preserving:

- `source_url` unchanged;
- legacy `document_id` under `source_native_ids`;
- platform, author, language and source text;
- engagement metadata;
- media references;
- raw reference;
- collection provenance.

Collection and Analysis may evolve their concrete Python implementations independently, but this adapter must remain contract-tested.

## Legacy compatibility

`from_ep24_legacy()` is a bounded compatibility adapter. It maps useful historical EP24 fields to structured data:

- `whisper_transcript`, language and translation -> `content.transcripts[]`;
- `ocr_1...ocr_6` -> `content.ocr[]`;
- `frame_analysis_1...frame_analysis_6` -> `content.frames[]` descriptions;
- `summary_analysis` -> `analysis.summary`;
- historical IDs -> `source_native_ids`.

Numbered columns are never canonical internal fields. Unmigrated legacy values may remain under `legacy` only as compatibility material; canonical analysis code must not depend on them.

## Archaeology decisions

| Source | Decision | Reason |
|---|---|---|
| `LaclauGPT/docs/CANONICAL_DATA_CONTRACT.md` | ADOPT | Normative cross-module contract and identity semantics. |
| `CyborgAnthropology/src/models.py` | ADAPT | Useful source-ingestion concepts map to `source`, `content` and media/raw references. |
| `LaclauGPT-Data-Collection/models.py` | ADAPT | Current producer contract is accepted at the boundary without making Collection a runtime dependency. |
| Existing Data Analysis `models.py` | ALREADY_IMPLEMENTED + ADAPT | NLP/topic/classification models remain useful derived objects; standalone forms now carry a source identity link. |
| `LaclauGPT-Multimodal-Analysis` | LEGACY_COMPATIBILITY_ONLY + ADAPT | Transcript/OCR/frame evidence is retained structurally; procedural Puhti pipeline and numbered columns are not. |
| `LaclauGPT-Discourse-Analysis` canonical/discourse concepts | ADAPT | Theory-facing concepts are represented in the `analysis` section with evidence, provenance and provisional review semantics. |
| private repositories/data/configuration | PRIVATE_DO_NOT_COPY | Only public-safe generic behavior belongs here. |
| backend-specific IDs and DataFrame row numbers | OBSOLETE as semantic identity | They may exist internally but cannot replace `source_url`. |

## Schema evolution

Current Analysis canonical schema version: `1.0.0`.

Any persisted semantic change must include a schema-version decision, migration note and synthetic round-trip tests. Do not silently reinterpret old records. Add explicit migration functions when a future version changes names, cardinality or meaning.

## Privacy

All tests and examples are synthetic. Runtime records, codebooks, transcripts, OCR, frames, researcher notes, databases and exports belong under the ignored `data/` tree or remote private infrastructure, never in Git.
