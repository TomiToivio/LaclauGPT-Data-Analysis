# Development branches and research phases

**Phases describe papers, not software.** "Phase 1–4" names the research programme's papers and their hypotheses, theory, methodology and analyses. Collection, Analysis and Visualization are one continuously maintained system, so a new paper adds requirements to the current modules rather than triggering a phase-specific codebase, pipeline or rewrite. See the umbrella `AGENTS.md`.

The active development branch is `main`. Create short-lived branches from `main` for fixes/features and merge validated PRs into `main`. No phase-specific Git branching, phase-branch mirroring or branch synchronization is required or expected.

The programme is currently working on **research Phase 1** (Paper 1). Paper 2 is optional and may be skipped; Papers 3 and 4 concern further interpretation, analysis and results produced by the same running system.

Existing `phase-N` branches may be retained as historical snapshots but must not control new work, and `main` must not be kept in sync with them. Do not delete or force-update historical branches without explicit authorization, and do not rename phase-bearing files, config keys or identifiers merely because they contain `phase`.

Preserve the repository's research-method, privacy, `TOMI-LOCKED`, reproducibility, and module boundary rules.
