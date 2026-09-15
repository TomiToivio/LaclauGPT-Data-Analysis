# LaclauGPT Data Analysis

[![tests](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/actions/workflows/tests.yml/badge.svg)](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/actions/workflows/tests.yml)

**LaclauGPT Data Analysis** is the analysis module of the modular LaclauGPT research framework. It contains storage-neutral analytical contracts and reusable NLP, embedding, topic-model, classification, multimodal and statistical backends.

The package works locally with CSV + SQLite + local files and can scale to MongoDB + Redis + S3-compatible object storage.

## Runtime data boundary

All runtime and study-specific material lives below `./data/`, which is entirely excluded from Git. See `docs/RUNTIME_DATA.md`.

Typical directories include `data/logs/`, `data/database/`, `data/config/`, `data/files/`, `data/csv/`, `data/jsonl/`, `data/codebooks/`, `data/sources/`, `data/downloads/`, `data/media/`, `data/models/ollama/`, `data/models/whisper/`, `data/cache/`, `data/tmp/`, `data/exports/`, `data/artifacts/`, `data/runs/`, `data/transcripts/`, and `data/frames/`.

The application should not create parallel top-level runtime roots such as `var/`, `logs/`, `outputs/`, or model-cache directories.

## Local-first configuration

Default paths:

- data root: `./data`
- SQLite: `sqlite:///./data/database/analysis.sqlite3`
- artifacts: `./data/artifacts`
- cache: in-memory

Example:

```bash
export LACLAUGPT_DATA_BACKEND=sqlite
export LACLAUGPT_DATABASE_URL=sqlite:///./data/database/analysis.sqlite3
```

If Collection runs as a sibling repository on the same machine:

```bash
export LACLAUGPT_COLLECTION_DATA_DIR=../LaclauGPT-Data-Collection/data
```

Analysis can then consume canonical Collection material directly without copying private data into either Git repository.

## Distributed/server configuration

For a server or multi-worker deployment, enable adapters independently:

```bash
export LACLAUGPT_PROFILE=server
export LACLAUGPT_DATA_BACKEND=mongodb
export LACLAUGPT_MONGO_URL='mongodb://HOST:27017'
export LACLAUGPT_MONGO_DATABASE=laclaugpt
export LACLAUGPT_CACHE_BACKEND=redis
export LACLAUGPT_REDIS_URL='redis://HOST:6379/0'
export LACLAUGPT_OBJECT_BACKEND=s3
export LACLAUGPT_S3_ENDPOINT_URL='https://OBJECT-STORAGE-ENDPOINT'
export LACLAUGPT_S3_BUCKET='BUCKET-NAME'
export LACLAUGPT_S3_REGION='REGION'
```

MongoDB carries canonical records, Redis carries coordination/cache/state where useful, and S3-compatible storage such as CSC Allas carries files and large artifacts. CSV/JSONL export/import remains the manual fallback.

## Architecture

Importable implementation lives under `src/laclaugpt_data_analysis/`. Heavy libraries remain optional and lazy. Descriptive computation is kept separate from discourse-theoretical interpretation, and interpretive claims should retain evidence, provenance and human review.

The useful backend layer from `LaclauGPT-Discourse-Analysis` has been adapted here, including spaCy, SentenceTransformers, scikit-learn, BERTopic, gensim, Transformers and statsmodels integrations.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e '.[dev]'
pytest
```

Optional extras:

```bash
pip install -e '.[analysis]'
pip install -e '.[nlp]'
pip install -e '.[topics]'
pip install -e '.[remote]'
```

## Interoperability

The local pipeline is Collection `data/` -> Analysis `data/` -> Visualization `data/`, connected by configured filesystem paths when everything runs on one machine.

Distributed deployments use MongoDB + Redis + S3/Allas. Manual CSV/JSONL transfer is supported. Storage backend choice must not alter the canonical schema, stable IDs or provenance semantics.

## Privacy and development

This is public code with private runtime data. Tests use synthetic fixtures only. Public examples contain placeholders; operational material belongs under `data/` or external deployment systems.

Before merging:

```bash
ruff check .
pytest --cov=laclaugpt_data_analysis --cov-report=term-missing
```

See `AGENTS.md`, `PRIVACY.md`, and `docs/RUNTIME_DATA.md` for the repository contract.

## License

See `LICENSE`.
