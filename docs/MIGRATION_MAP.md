# Migration map — LaclauGPT-Data-Analysis (issue #2)

Source: `TomiToivio/LaclauGPT-Discourse-Analysis` (monolith).
Classifications: `MIGRATE` / `ALREADY_IMPLEMENTED` / `REFACTOR-REIMPLEMENT` /
`OUT_OF_SCOPE` / `PRIVATE_DO_NOT_COPY`.

## 1. Ollama / LLM runtime

| Source path | Classification | Destination | Notes |
|---|---|---|---|
| `laclaugpt/llm.py` | MIGRATE | `llm/base.py`, `llm/ollama.py` | provider protocol; `ollama` lazy-imported inside the provider; deterministic options (temperature 0); provenance per call |
| `laclaugpt/model_routing.py` | MIGRATE | `llm/routing.py` | stage routing, `LACLAUGPT_MODEL_<STAGE>` overrides, capability-order fallback, resolved-tag provenance |
| `run_config.py` (analysis parts) | REFACTOR-REIMPLEMENT | `config.py` + llm settings | environment/profile driven; no machine paths |
| structured-output handling | MIGRATE | `llm/structured_output.py` | parsing/validation of model JSON output |

## 2. Analysis pipeline / backends

| Source path | Classification | Destination | Notes |
|---|---|---|---|
| `laclaugpt/model/` (7 Pydantic types + store + projections) | ALREADY_IMPLEMENTED (concept) / REFACTOR | `models.py`, `storage.py` | destination contracts (`Provenance`, `Representation`, `EntityMention`, `Topic`, …) kept backend-neutral; legacy v1 fields map at adapters |
| `laclaugpt_interchange/` (schema 1.7) | OUT_OF_SCOPE (stays in monolith) | — | interchange remains the monolith's external-exchange pivot; mapping documented; Analysis emits canonical analysis results per the cross-module spec |
| `laclaugpt_primitives/` | MIGRATE (vocab concepts) | `memory/models.py` | kinds/states/normalisation vocabulary |
| NLP/topic/statistics backends | ALREADY_IMPLEMENTED | `analysis/*_backend.py` | pre-existing destination backends kept; lazy imports, capability extras |
| discourse-theoretical candidate generation / stage orchestration | MIGRATE (staged) | pipeline orchestration on the provider protocol | stage routing via `llm/routing.py`; evidence-first coding; abstention paths preserved |
| provenance generation | ALREADY_IMPLEMENTED | `models.Provenance` | per-call LLM provenance in `llm/base.py` |
| uncertainty/review semantics | ALREADY_IMPLEMENTED | `models.py` review_status fields | INV_HUMAN_REVIEW |

## 3. Memory / codebook stack

| Source path | Classification | Destination | Notes |
|---|---|---|---|
| `laclaugpt_memory/` (`Memory`, 842 lines: resolution ladder exact→alias→fuzzy→embedding, stable IDs E/T/S/C/A/F, states, temporal table, decisions log) | MIGRATE | `memory/` package | two-layer separation preserved: persistent SQLite stable-ID store + runtime context orchestration |
| `laclaugpt/memory/context.py` (CanonicalRegistry, EntityResolver, ContextBuilder, MemoryTrustModel) | MIGRATE | `memory/context.py` (runtime layer) | repository-aware context selection for prompts |
| `laclaugpt/context_policy.py` | MIGRATE | `memory/context.py` | trust model / context selection policy |
| `seed_codebook.py` | MIGRATE (methodology) | `codebooks/public/seed_ai_formations.md` + seed loader | seeds are PROVISIONAL; non-adjudicative definitions preserved |
| `sources/codebooks/ai_spiralism.md` | MIGRATE (public/methodological) | `codebooks/public/ai_spiralism.md` | exploratory sensitising category; collection config referenced as private, not copied |
| `sources/codebooks/legacy_finland.md` | PRIVATE_DO_NOT_COPY | — | grounded in legacy research-diary rows (158 FI identifier rows) and unpublished mappings: study-specific research data |
| `sources/codebooks/legacy_poland.md` | PRIVATE_DO_NOT_COPY | — | same: 160 diary rows, unpublished entity mappings |
| `laclaugpt/formations.py` CANONICAL_FORMATIONS | MIGRATE (vocabulary) | `codebooks/public/seed_ai_formations.md` | six sensitising formation labels |

## 4. Deliberately excluded

| Source path | Reason |
|---|---|
| `collector/` | belongs to LaclauGPT-Data-Collection (issue #2 there) |
| `laclaugpt/visualization/` | belongs to LaclauGPT-Data-Visualization |
| `dashboard/`, simulation, paper/ | out of scope for the analysis module |
| private study configs / data roots | never copied (privacy rules) |

## Architecture decisions

1. **Provider boundary:** pipeline stages depend on the `LLMProvider`
   protocol; Ollama is one lazy backend. No network/model call at import
   time.
2. **Memory two layers:** persistent SQLite stable-ID store
   (`memory/store.py`, `memory/sqlite.py`) vs runtime context orchestration
   (`memory/context.py`). One package API over both.
3. **Canonical destination contracts win:** where monolith and destination
   models disagree, the destination's backend-neutral contracts win and the
   monolith shapes are mapped at boundary adapters.
4. **Codebook privacy:** public methodology committed; diary-grounded legacy
   codebooks stay out of Git (classification table above).