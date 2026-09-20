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

Persistent stable-ID memory is separate from runtime retrieval. `SQLiteMemory` is the zero-infrastructure default for canonical actors, entities, topics, signifiers, targets and formations plus aliases. IDs can be derived deterministically from normalized kind + label with `stable_memory_id()`.\n\nResolution is conservative: an exact normalized alias resolves only when it identifies one object; collisions return `AMBIGUOUS` instead of choosing arbitrarily. New proposals are `PROVISIONAL` by default. Only an explicit review transition (`accept()` / `set_state()`) makes an object `CANONICAL`, and automatic runtime normalization reads only `CANONICAL` objects.\n\n`analyze_record(..., memory_store=...)` applies accepted memory as an optional final normalization layer. It may replace ephemeral entity/topic/signifier IDs and records the stable IDs in `analysis.memory_refs`; accepted source-author actor IDs are recorded as continuity refs without rewriting source metadata. The normalization step never creates or promotes memory, never changes evidence, and is independently reversible by omitting the store. Memory/codebook context is continuity/normalization, never source evidence.

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
