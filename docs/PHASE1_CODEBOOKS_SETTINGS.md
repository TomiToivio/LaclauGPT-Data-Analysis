# Phase 1 codebooks and settings

Phase 1 configuration is an executable research protocol rather than an informal collection
of YAML files. The public repository defines the contract, safe defaults and methodological
vocabulary; study-sensitive material remains private.

## Composition order

1. `config/phase1/defaults.yaml`
2. public study profile such as `config/phase1/ai26.yaml`
3. optional private study overlay
4. optional machine overlay
5. optional execution overlay

Later layers override earlier ones. The resulting mapping is canonicalized and SHA-256
fingerprinted. The codebook bundle is fingerprinted independently. These hashes map directly
to the existing `config_revision` and `codebook_revision` provenance fields.

## Codebook lifecycle

Entries have both a state and provenance. `authoritative` is for theory or researcher
controlled entries. `discovered` + `model` means a model-produced candidate. `derived`
is an analytical output. Model candidates are never silently promoted to authoritative
research entries.

Public codebooks contain methodology, conceptual taxonomies and synthetic examples only.
Real account lists, study actors, researcher classifications, diary material, private
source mappings, credentials, deployment secrets and sensitive metadata belong in
`LaclauGPT-Private` or another explicitly configured private path.

## AI26

`config/phase1/ai26.yaml` is a public, non-sensitive profile. It names the study dimensions
and configurable formations but contains no private source/account lists. The formations are
research categories, not truth labels.

## Operator commands

```bash
laclaugpt-phase1-config config validate --profile ai26
laclaugpt-phase1-config config render --profile ai26
laclaugpt-phase1-config config fingerprint --profile ai26
laclaugpt-phase1-config codebook validate
laclaugpt-phase1-config codebook fingerprint
```

`render` recursively redacts keys that look like credentials/secrets.

For private runs, add `--private-overlay PATH`, and optionally machine/execution overlays.
Private overlays must never be reconstructed from model memory when authoritative files are
missing.

## Validation and cache safety

Validation rejects unsupported schema/phase values, missing required sections, invalid IDs,
duplicate IDs, alias collisions, dangling references and attempts to mark model-originated
entries as authoritative. Serialization order does not affect fingerprints. Meaningful
config or codebook edits do, allowing existing cache/task code to identify stale results.

## Phase isolation

This implementation lives on Phase 1 and does not add imports or dependencies to Phase 0.
The Phase 0 branch remains the reproducible Phase 0 implementation.
