# Issue #19 source audit

This audit records the generic/public-safe discourse-analysis runtime pieces reviewed before implementation. Private study values, source lists, credentials, machine paths, unpublished annotations and operational codebooks are intentionally excluded.

| source path | capability | exists now? | decision | target path | privacy notes |
|---|---|---|---|---|---|
| `LaclauGPT-Discourse-Analysis/laclaugpt/config.py` | canonical project -> arena -> machine -> execution composition and explicit overrides | partial | adapt | `src/laclaugpt_data_analysis/runtime_config.py` | generic composition only; callers may supply private files externally |
| `LaclauGPT-Discourse-Analysis/laclaugpt/context_profiles.py` | `fast_local`, `balanced`, `high_accuracy`, `validation` bounded policies | no | port/adapt | `src/laclaugpt_data_analysis/context_profiles.py` | public policy definitions contain no study data |
| `LaclauGPT-Discourse-Analysis/laclaugpt/context_runtime.py` | bounded codebook/previous-state/corpus context plus context provenance | partial | adapt | `src/laclaugpt_data_analysis/context_runtime.py` | runtime accepts already-loaded items and performs no network access |
| `LaclauGPT-Data-Analysis/memory/` | local durable memory and deterministic retrieval | yes | keep | existing `memory/` package | no second memory system created |
| `LaclauGPT-Data-Analysis/codebooks.py` | JSON codebook loading and memory seeding | yes, basic | extend | `src/laclaugpt_data_analysis/codebooks.py` | adds YAML, validation, selection/merge and content fingerprints; private books stay external |
| `LaclauGPT-Discourse-Analysis-Private` project/arena/codebooks | mature study-specific runtime values | private only | reject values, retain patterns | external runtime configuration | never copied to public repository |
| issue #17 RAG work | optional graph/vector context | separate work | integration boundary only | `ContextItem` / `rag_context` input | RAG stays optional and disabled by default in bundled profiles |

## Design decisions

1. The effective configuration is immutable/read-only after composition and receives a stable SHA-256 hash.
2. Public provenance records identities, hashes and selected profiles, not private file paths or private configuration contents.
3. Context assembly is deterministic and offline: retrieval services feed `ContextItem` records into the runtime rather than being hidden inside prompt concatenation.
4. Existing local memory remains authoritative. This change adds a policy/envelope around context sources, not another database.
5. Context profiles impose record/character/token-hint budgets and explicitly decide whether prior summaries, corpus statistics, researcher validation, theory context and future RAG results may be used.
6. Validation mode fails closed when a required codebook is absent.
7. Codebooks can be layered and fingerprinted. Human-curated actor/entity additions may be supplied by external project/arena codebooks.
8. Study-specific analysis-stage switches and model choices remain ordinary configuration values, not hard-coded package behavior.

## Provenance fields supported

`EffectiveRunConfig.provenance()` provides a publication-safe snapshot containing project, arena, machine/execution profiles, effective configuration hash, context profile, codebook descriptor, model routing, storage/backend selection, RAG usage flag, pipeline version and source-file fingerprints.

`ContextSnapshot.provenance` records the selected context profile, bounded item count/size, context fingerprint and per-item source IDs/trust metadata. Operational directory paths are not recorded.

`Codebook.provenance_snapshot()` records codebook ID, version, SHA-256 fingerprint, project/arena selectors and entry count.
