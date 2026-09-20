# Phase 1 legacy code audit and quarantine

Issue: #224  
Parent plan: #200, Step 11  
Branch policy: Phase 1 only. This audit must not change Phase 0 or promote work into `main`.

## Decision

No legacy code is deleted by this issue.

The canonical Phase 1 architecture now covers much of the behavior historically carried by the `laclaugpt/puhti_*.py` scripts, but several preceding Phase 1 reactivation issues are still open. Under the Step 11 rollback rule, that means the legacy executables remain **quarantined compatibility/reference material** until the corresponding replacement paths are operationally proven.

The machine-readable inventory is `docs/legacy_phase1_inventory.yaml`. It uses all three Step 11 classifications:

- **keep**: retain as documentation/reproducibility material.
- **adapt**: keep the artifact active only where it is itself part of the canonical compatibility/runtime path, or migrate its assumptions into canonical documentation/runtime.
- **delete_after_replacement**: the legacy artifact is an eventual deletion candidate, but remains quarantined until a later dedicated issue proves every replacement dependency.

## Current inventory

| Legacy item | Classification | Canonical home | Current state |
| --- | --- | --- | --- |
| `laclaugpt/puhti_preprocess.py` | delete after replacement | `multimodal` adapters and deterministic frame/evidence handling | quarantined |
| `laclaugpt/puhti_frame.py` | delete after replacement | canonical multimodal evidence + `ep24.frame_analysis:v2` | quarantined |
| `laclaugpt/puhti_summary.py` | delete after replacement | canonical pipeline + `ep24.summary_analysis:v2` | quarantined |
| `laclaugpt/puhti_postprocess.py` | delete after replacement | canonical exporters/postprocess prompt | quarantined |
| `laclaugpt/puhti_populism.py` | delete after replacement | canonical Laclau analysis + plugin runtime | quarantined |
| `docs/legacy_ep24_prompts/` | keep | versioned canonical EP24 prompt library | reference-only |
| `docs/EP24_LEGACY_PROMPTS.md` | keep | prompt provenance/migration documentation | reference-only |
| `docs/MULTIMODAL_MIGRATION.md` | keep | migration map itself | active documentation |
| `LegacyLaclauPlugin` | adapt | canonical plugin runtime | active compatibility |
| direct `puhti_*` examples in `laclaugpt/README.md` | adapt | canonical runtime docs | historical notes, not entry points |

## Replacement evidence already present

The audit found regression coverage for important legacy behavior rather than assuming replacement from code shape alone:

- `tests/test_multimodal.py` and `tests/test_issue_220_optional_multimodal.py` cover optional multimodal behavior and the text-only boundary.
- `tests/test_legacy_discourse_parity.py` pins substantive legacy discourse/prompt obligations against the canonical pipeline.
- `tests/test_phase1_shadow_bridge.py` covers Phase 0 → canonical adaptation and provider-free shadow preprocessing.
- `tests/test_phase1_text_runtime.py` covers opt-in Phase 1 summary/discourse behavior, namespaced persistence, and the Visualization handoff.
- `tests/test_plugin_pipeline.py` covers the compatibility Laclau adapter inside the canonical plugin runtime.
- `tests/test_mongodb_rag_context.py` covers provenance-tagged RAG context and the source-evidence boundary.

These tests justify classification and quarantine. They do **not** by themselves authorize deleting the historical scripts while predecessor activation/integration work remains incomplete.

## Active dependency boundary

`pyproject.toml` packages only `src/laclaugpt_data_analysis` and exposes canonical console entry points. None of the project scripts target `laclaugpt/puhti_*.py`.

`tests/test_issue_224_legacy_quarantine.py` makes that boundary executable:

1. every inventory path must exist;
2. every delete-after-replacement candidate must have named regression coverage;
3. no packaged console entry point may resolve to a `puhti_*` module;
4. canonical runtime source under `src/laclaugpt_data_analysis` may not import legacy `puhti_*` modules, either package-qualified or as direct modules;
5. deletion remains disabled in the inventory for this issue.

This turns “legacy is reference-only” from a comment into a CI-enforced architectural constraint.

## Deletion gate for a future issue

A later deletion issue may remove a candidate only when all of the following are true:

1. the corresponding canonical replacement is enabled and tested on its intended project profile;
2. relevant predecessor Phase 1 issues are completed or explicitly superseded;
3. regression tests cover the legacy behavior that still matters scientifically;
4. no packaged entry point, canonical module, deployment script, or active documentation runbook depends on the candidate;
5. removing the file does not weaken Phase 0 tests or make multimodal support a requirement for text-only AI26;
6. the deletion is performed separately from capability activation/refactoring.

Until then, the correct state is **quarantine, not deletion**.

## Outcome

Issue #224 is therefore an inventory/audit implementation. It clarifies which artifacts are scientific provenance, which behavior is being absorbed by canonical components, and which executables are eventual deletion candidates, while changing no runtime capability and leaving Phase 0 untouched.
