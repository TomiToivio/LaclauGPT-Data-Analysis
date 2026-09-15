# Analysis runtime architecture

This repository is the canonical reusable analysis runtime for modular LaclauGPT.

## Flow

```text
CanonicalRecord
  -> codebook / persistent memory retrieval
  -> provider-neutral LLM analysis
  -> validated structured proposal
  -> canonical analysis fields + provenance + provisional review state
  -> serializable canonical record
```

## LLM providers

`llm/base.py` defines the provider contract. `llm/ollama.py` is a lazy optional implementation. Importing the package never contacts Ollama or downloads a model.

Model routing is explicit. Laptop defaults to a small local Gemma 4 profile, Linux server to `gemma4:12b`, and Roihu/HPC to `gemma4:26b`; callers may override. Cloud models require explicit `cloud_allowed=True`. There is no silent local-to-cloud fallback.

## Memory

Persistent stable-ID memory is separate from runtime retrieval. `SQLiteMemoryStore` is the zero-infrastructure default. Entries carry aliases, provenance references, temporal bounds and review state. Retrieval returns candidates and may abstain. Retrieved memory/codebook candidates are context, never evidence.

## Codebooks

Machine-readable codebooks use versioned JSON and `MemoryEntry` records. Public conceptual codebooks and synthetic examples may be committed. Study-specific codebooks belong under ignored `data/codebooks/` or private/external storage.

## Migration map

| Monolith source | Decision | New home |
| --- | --- | --- |
| `llm.py` | REFACTOR/REIMPLEMENT | `llm/base.py`, `llm/ollama.py`, `llm/routing.py` |
| `laclaugpt/model_routing.py` | REFACTOR/REIMPLEMENT | `llm/routing.py` |
| `pipeline.py` | REFACTOR/REIMPLEMENT | small `pipeline.py` orchestration over canonical records |
| `laclaugpt/memory/` | MIGRATE concept | `memory/` |
| `laclaugpt_memory/` | CONSOLIDATE | `memory/` only, no duplicate package |
| `context_runtime.py`, `context_profiles.py` | ADAPT | provider-independent retrieval/context APIs; deployment profiles stay configuration-side |
| `seed_codebook.py` | ADAPT | `codebooks.py::seed_memory` |
| public `sources/codebooks/` | ADAPT selectively | `codebooks/public/` and versioned machine-readable forms |
| study/private codebooks and researcher annotations | PRIVATE_DO_NOT_COPY | ignored runtime/private storage |
| `laclaugpt_interchange/`, primitives | ALREADY_IMPLEMENTED / CONSOLIDATED | canonical record and existing analysis models |
| collection/scraping/browser code | OUT_OF_SCOPE | Data Collection |
| dashboards | OUT_OF_SCOPE | Data Visualization |

## Review semantics

LLM-generated theory-facing outputs remain provisional. The pipeline does not turn retrieved codebook candidates into source evidence, and uncertainty/abstention is preserved explicitly.

## Testing

Normal CI uses fake providers and synthetic records. Real Ollama, MongoDB, Redis, S3/Allas and CSC services are optional and must never be required for unit tests.
