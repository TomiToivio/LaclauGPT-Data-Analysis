# LaclauGPT Data Analysis

[![tests](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/actions/workflows/tests.yml/badge.svg)](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/actions/workflows/tests.yml)

**LaclauGPT Data Analysis** is the analysis module of the modular LaclauGPT research framework. It contains storage-neutral analytical contracts and reusable NLP, embedding, topic-model, classification and statistical backends. Collection, durable storage and visualization belong in sibling repositories.

The package is designed to work on a laptop with **CSV + SQLite + local files by default** and to scale to **MongoDB + Redis + S3-compatible object storage** when a project needs distributed infrastructure.

## Architecture

This repository follows a conventional modern Python package layout:

```text
.
├── .github/workflows/tests.yml
├── src/laclaugpt_data_analysis/
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── bertopic_backend.py
│   │   ├── gensim_backend.py
│   │   ├── sentence_transformers_backend.py
│   │   ├── sklearn_backend.py
│   │   ├── spacy_backend.py
│   │   ├── statsmodels_backend.py
│   │   └── transformers_backend.py
│   ├── config.py
│   ├── models.py
│   └── storage.py
├── tests/
├── .env.example
├── PRIVACY.md
└── pyproject.toml
```

The analysis interfaces intentionally separate **descriptive computation** from **discourse-theoretical interpretation**. Embedding similarity is not equivalence; a topic cluster is not a discourse; classifier confidence is not theoretical confidence. Interpretive claims should retain evidence, provenance and human review in the wider LaclauGPT workflow.

## Reused analysis code

The useful backend layer from [`TomiToivio/LaclauGPT-Discourse-Analysis`](https://github.com/TomiToivio/LaclauGPT-Discourse-Analysis) has been ported and adapted here:

- spaCy: tokens, POS, dependencies and entity-mention candidates
- SentenceTransformers: multilingual embeddings and similarity
- scikit-learn: NMF/KMeans topic baselines and TF-IDF classifiers
- BERTopic: embedding-based topic candidates
- gensim: LDA/LSI/HDP baselines
- Hugging Face Transformers: configurable classification/NER inference
- statsmodels: statistical inference on reviewed corpus-level datasets

The port fixes contract mismatches found in the older integrated implementation and keeps heavyweight libraries optional.

## Install

Minimal local installation:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e '.[dev]'
pytest
```

Install analytical extras as needed:

```bash
pip install -e '.[analysis]'
pip install -e '.[nlp]'
pip install -e '.[topics]'
pip install -e '.[remote]'
# or everything
pip install -e '.[all]'
```

Optional libraries are imported lazily. The base package and tests do not require spaCy, PyTorch, BERTopic, MongoDB, Redis or S3 clients.

## Local-first configuration

No configuration is required for the default laptop profile:

- tabular records: CSV
- relational/local state: SQLite is available via `LACLAUGPT_DATA_BACKEND=sqlite`
- artifacts: `./var/artifacts`
- cache: in-memory
- generated/runtime data: `./var/` (gitignored)

Configuration is read from `LACLAUGPT_*` environment variables. Copy `.env.example` only as a reference; `.env` itself is gitignored and should never be committed.

Example SQLite mode:

```bash
export LACLAUGPT_DATA_BACKEND=sqlite
export LACLAUGPT_DATABASE_URL=sqlite:///./var/laclaugpt.db
```

## Distributed/server configuration

For a server, CSC environment or multi-worker deployment, enable adapters independently:

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

S3-compatible storage is suitable for services such as CSC Allas. Credentials should come from the runtime environment or secret-management tooling, never from committed files.

## Interoperability with other LaclauGPT modules

This repository should remain usable independently while exchanging plain, versionable records with the other core modules:

- [LaclauGPT Data Collection](https://github.com/TomiToivio/LaclauGPT-Data-Collection): produces source/representation records
- **LaclauGPT Data Analysis**: produces analytical annotations, candidates, embeddings, statistics and provenance
- [LaclauGPT Data Visualization](https://github.com/TomiToivio/LaclauGPT-Data-Visualization): consumes analysis outputs without importing analysis internals

Prefer JSON-compatible dictionaries/Pydantic models, stable IDs and explicit provenance at module boundaries. Do not make another LaclauGPT repository import a private implementation detail from `analysis/*` when a serialized contract will do.

## Privacy: public code, private data

**Do not commit research data or real configuration.** See [`PRIVACY.md`](PRIVACY.md) for the full policy.

The repository ignores common datasets, SQLite databases, generated artifacts, `.env*`, keys and machine-specific config. That is defense in depth, not permission to stage sensitive material. Before every push, inspect `git status` and `git diff --cached`.

Tests must use synthetic data only.

## Development standards

- Python 3.11+
- `src/` package layout
- `pyproject.toml` as package/tool configuration
- type hints on public interfaces
- optional dependencies grouped by capability
- deterministic analytical defaults where practical
- Ruff for linting
- pytest for tests
- GitHub Actions on Python 3.11, 3.12 and 3.13
- no import-time requirement for heavyweight/remote services
- no secrets, research datasets or machine-specific configuration in Git

Run locally:

```bash
ruff check .
pytest --cov=laclaugpt_data_analysis --cov-report=term-missing
```

## License

See [`LICENSE`](LICENSE).
