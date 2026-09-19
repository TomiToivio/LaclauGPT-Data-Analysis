# LaclauGPT Data Analysis

[![tests](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/actions/workflows/tests.yml/badge.svg)](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/actions/workflows/tests.yml)

> **Part of the [LaclauGPT](https://github.com/TomiToivio/LaclauGPT) project.** The main LaclauGPT repository is the **meta-repository** and project front door: it contains the scientific paper, theory, shared architecture, canonical data contract and complete-system documentation. This repository is only the **Data Analysis** implementation stage.
>
> **Project map:** [LaclauGPT / paper + meta-repo](https://github.com/TomiToivio/LaclauGPT) → [Data Collection](https://github.com/TomiToivio/LaclauGPT-Data-Collection) → **Data Analysis (you are here)** → [Data Visualization](https://github.com/TomiToivio/LaclauGPT-Data-Visualization)

**LaclauGPT** is an open social-science research framework for **LLM-assisted computational discourse analysis** of large textual and multimodal corpora. It combines computational methods with interpretive political research while keeping model outputs traceable to source evidence, uncertainty, provenance and human review.

The current flagship research programme is **[LaclauGPT: Ideological contestation over AI](https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md)**. The canonical theoretical and methodological contract is **[THEORY.md](https://github.com/TomiToivio/LaclauGPT/blob/main/THEORY.md)**.

The framework is developed around Ernesto Laclau and Chantal Mouffe's discourse theory and Emilia Palonen's work on populism, polarisation and hegemonic dynamics. The AI/AGI study is the main development case, but LaclauGPT is a **general research framework rather than a single-purpose AI ideology classifier**. The same architecture can support election research, populism, grievance politics, social-media research and other comparative discourse-analysis projects.

> [!WARNING]
> **Human-in-the-loop academic research only.** LaclauGPT's machine-generated summaries, classifications, discourse-theoretical codes, populism analyses, signifier roles, ideological formations, affects and other interpretations are **preliminary analyses to be verified by a human researcher**. They must not be treated as final findings, ground truth or autonomous scholarly judgement. Human verification of source evidence and interpretation is required before results are reported, published or cited as research conclusions. LaclauGPT is designed for academic research, not autonomous operational, administrative, intelligence, moderation, profiling or policy decisions about people or groups.

## Research philosophy: human-in-the-loop as an assemblage

LaclauGPT uses a deliberately assemblage-based working philosophy of AI:

> **AI = HUMAN + LLM + LANGUAGE + INTERNET**

This is a methodological and philosophical framing, not a settled empirical claim about machine consciousness.

- **HUMAN — interpretation and accountable agency.** Researchers choose questions, define concepts and codebooks, evaluate evidence, resolve ambiguity, reject model output and remain responsible for conclusions.
- **LLM — learned model plus agentic machinery.** Models may contribute structured proposals, retrieval, comparison, tool use and iterative analysis, but their outputs remain fallible and provisional.
- **LANGUAGE — communication protocol and cognitive medium.** Language couples the researcher, model, sources and analytical concepts, and helps constitute the distinctions and relations through which interpretation proceeds.
- **INTERNET — infrastructure and epistemic environment.** Networks, software, model repositories, databases, APIs and research corpora form part of the practical research system. Retrieved information remains evidence to evaluate, not automatically trusted truth.

Human-in-the-loop therefore means more than a final manual approval button. The human researcher is constitutive of the research assemblage throughout the process.

## Theoretical and methodological orientation

LaclauGPT treats political meaning as **relational, contested and only partially fixed**. The goal is not merely to detect topics, sentiment or frequently occurring words, but to investigate how meanings, identities, demands, signifiers and political frontiers are articulated in relation to one another.

The framework can propose evidence for concepts such as articulations, nodal points, floating and empty signifiers, equivalential and differential relations, collective subjects, antagonistic frontiers, affective investment, ideological formations, myths, imaginaries and hegemonic dynamics. These are **theoretical roles supported by evidence**, not labels inferred mechanically from keywords or frequency.

Key methodological cautions include:

- frequency is not hegemony;
- semantic similarity is not equivalence;
- negative sentiment is not antagonism;
- polysemy or vagueness is not empty signification;
- mentioning "the people" is not automatically populism;
- document-level evidence does not by itself establish a corpus-level ideological formation.

The model may propose interpretations, but researchers must be able to inspect the source passage, reject or revise a coding, compare alternative readings, mark uncertainty and validate corpus-level claims. **Abstention and empty outputs are legitimate results when evidence is insufficient.**

See the **[scientific paper](https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md)** and **[theory contract](https://github.com/TomiToivio/LaclauGPT/blob/main/THEORY.md)** for the full conceptual framework.

## This repository

**LaclauGPT Data Analysis** is the canonical reusable analysis engine of the modular LaclauGPT research framework. It turns canonical source records produced by **[LaclauGPT Data Collection](https://github.com/TomiToivio/LaclauGPT-Data-Collection)** into evidence-linked, structured and human-reviewable analytical proposals, which can then be explored in **[LaclauGPT Data Visualization](https://github.com/TomiToivio/LaclauGPT-Data-Visualization)**. The scientific paper, theory and project-wide contracts live in the **[LaclauGPT meta-repository](https://github.com/TomiToivio/LaclauGPT)**.

It contains storage-neutral analytical contracts, NLP/embedding/topic/classification/multimodal/statistical backends, a provider-neutral LLM runtime, codebook/context-memory machinery and canonical-record orchestration.

The package works locally with CSV + SQLite + local files and can scale to MongoDB + Redis + S3-compatible object storage.

## Phase 1 default analysis pipeline

Phase 1 follows the legacy LaclauGPT multimodal stage order while using the current canonical schemas, evidence rules and AI26 methodology:

```text
preprocessing
  -> frame analysis (only when image/video frames exist)
  -> summary analysis
  -> Laclaudian discourse analysis
  -> postprocessing
```

The default AI26 path uses AI26-specific multimodal and discourse prompts. EP24 is an explicit project profile with its own election-specific prompt templates. Model outputs remain provisional, evidence-linked pre-analysis for human review.

DNA, SNA, Critical AI Studies and other advanced methods are Phase 2 / experimental / optional. They are disabled by default and are not allowed to enter the Phase 1 canonical runner silently.

The postprocessing stage runs after Laclaudian analysis and normalizes the richer summary/discourse outputs into validated canonical fields for export, validation, comparison and visualization. It does not replace the summary or discourse analysis.

## Plugin-first analysis runtime

The core runtime follows one stable shape:

```text
CanonicalRecord
  -> PREPROCESS (generic representation normalization)
  -> [PLUGIN -> PLUGIN -> ... -> PLUGIN]
  -> POSTPROCESS (generic validation / projection / export)
```

Preprocess and postprocess remain generic and stable. The middle stage may contain zero, one or many analytical methods. Laclau/Mouffe analysis is therefore one plugin rather than a mandatory shape for every workflow.

`src/laclaugpt_data_analysis/plugin_pipeline.py` provides the versioned plugin contract, capability/dependency checks, registry and Python entry-point discovery, record- and corpus-level scopes, namespaced results, failure isolation and stable postprocessing. Plugin output lives under `analysis.plugin_results[plugin_name]`, with failures under `analysis.plugin_failures[plugin_name]`, while raw capture, intermediate data, evidence and provenance remain intact.

External plugin packages can use the entry-point group `laclaugpt.analysis_plugins`. Existing first-party methods such as Luhmann, DNA/SNA, Bourdieu/GDA, topic modelling and framing can migrate through thin adapters without rewriting the three-module deployment architecture.

See **[docs/PLUGIN_PIPELINE.md](docs/PLUGIN_PIPELINE.md)** for the plugin contract, examples, migration guidance and the distinction between generic preprocessing and analytical framing.

## Analysis runtime details

The reusable monolith analysis behavior is re-homed behind clean boundaries:

```text
CanonicalRecord
  -> codebook / stable-ID memory retrieval
  -> LLMProvider (Ollama is one optional adapter)
  -> validated structured proposal
  -> canonical analysis fields + uncertainty + provenance
  -> provisional human-reviewable output
```

`src/laclaugpt_data_analysis/llm/` owns provider contracts, Ollama and model routing. `memory/` owns stable-ID persistent memory and retrieval. `codebooks.py` owns machine-readable codebook validation/seeding. Existing canonical pipeline code remains available and can be wrapped as a plugin through `LegacyLaclauPlugin`.

Ollama is optional:

```bash
pip install -e '.[ollama]'
```

Importing the base package never contacts Ollama or downloads a model. Cloud inference must be explicitly allowed and is never a silent fallback. See `docs/ANALYSIS_RUNTIME.md` for the architecture and migration map.

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

## Codebooks and memory

Public conceptual codebooks and synthetic examples may be committed under `codebooks/public/` and `codebooks/examples/`. Private study-specific codebooks, entity/target lists and researcher annotations belong under ignored `data/codebooks/` or external/private storage.

Persistent memory uses stable IDs and review/provenance metadata. SQLite is the zero-infrastructure default. Retrieval returns candidates and may abstain. Retrieved memory/codebook material is context, not source evidence.

## Architecture

Importable implementation lives under `src/laclaugpt_data_analysis/`. Heavy libraries remain optional and lazy. Descriptive computation is kept separate from discourse-theoretical interpretation, and interpretive claims retain evidence, provenance and human review.

The “WordPress for social data science” idea is a plugin/modularity metaphor only. Collection, Analysis and Visualization stay independently deployable because their browser, GPU/batch and UI requirements differ. The plugin framework standardizes Analysis internals and contracts; it does not collapse the three modules into one service.

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
# Phase 1 research baselines only; not part of Phase 0/default runtime
pip install -e '.[phase1-nlp]'
pip install -e '.[ollama]'
pip install -e '.[remote]'
```

## Interoperability

The local pipeline is **[Collection](https://github.com/TomiToivio/LaclauGPT-Data-Collection)** `data/` → Analysis `data/` → **[Visualization](https://github.com/TomiToivio/LaclauGPT-Data-Visualization)** `data/`, connected by configured filesystem paths when everything runs on one machine. The shared schema and cross-module rules are governed by **[LaclauGPT](https://github.com/TomiToivio/LaclauGPT)**.

Distributed deployments use MongoDB + Redis + S3/Allas. Manual CSV/JSONL transfer is supported. Storage backend choice must not alter the canonical schema, stable IDs or provenance semantics.

## Privacy and development

This is public code with private runtime data. Tests use synthetic fixtures only. Public examples contain placeholders; operational material belongs under `data/` or external deployment systems.

Normal CI uses fake LLM providers. Real Ollama integration, if tested, must remain opt-in.

Before merging:

```bash
ruff check .
pytest --cov=laclaugpt_data_analysis --cov-report=term-missing
```

See `AGENTS.md`, `PRIVACY.md`, `docs/RUNTIME_DATA.md`, `docs/ANALYSIS_RUNTIME.md`, `docs/PLUGIN_PIPELINE.md`, and `docs/PHASE1_OPEN_SOURCE_LIBRARIES.md` for the repository contract and the dormant Phase 1 open-source library layer.

## License

See `LICENSE`.