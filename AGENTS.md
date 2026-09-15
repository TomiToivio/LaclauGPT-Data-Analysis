# Agent guidance

This is the **public LaclauGPT Data Analysis** repository. Keep it publication-safe and narrowly scoped.

## Scope

This repository owns reusable analysis code: analytical contracts, NLP/embedding/topic/classification/statistical backends, analysis orchestration and thin boundary adapters needed to read/write analysis inputs and outputs.

Do not add collectors, browser automation, scrapers, dashboards or project-specific research data here. Those belong in sibling LaclauGPT modules or private project repositories.

## Python architecture

- use the `src/laclaugpt_data_analysis/` package
- keep public contracts in small storage-neutral modules
- depend on protocols/contracts rather than concrete remote services
- keep optional/heavy libraries behind lazy imports and capability extras
- keep local CSV/SQLite/filesystem/in-memory operation working without remote infrastructure
- add optional MongoDB/Redis/S3 behavior through adapters, not hard-coded dependencies
- do not perform network connections or model downloads at import time
- prefer deterministic defaults and explicit model/version provenance
- add or update tests for behavioral changes
- keep Ruff and pytest green on supported Python versions

## Methodological boundary

Computational outputs are evidence or candidates. Topic clusters are not automatically discourses; embedding similarity is not equivalence; model confidence is not theoretical confidence. Theory-facing classifications should remain traceable to evidence, provenance and human review in the wider LaclauGPT workflow.

## Privacy

Read `PRIVACY.md` before touching data/config paths. Never commit research data, row-level exports, transcripts, media, credentials, `.env` files, private codebooks or machine-specific secrets. Tests use synthetic data only.

When adding configuration, add safe variable names/placeholders to `.env.example`; real values stay outside Git.

## Interoperability

Prefer plain JSON-compatible records, stable IDs and explicit schema/provenance fields at boundaries with Data Collection, Data Storage and Data Visualization. Avoid cross-repository imports of implementation internals.
