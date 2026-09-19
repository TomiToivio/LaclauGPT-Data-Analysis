# Phase 1 open-source analysis libraries

This integration is intentionally dormant during Phase 0. The default install and canonical runner are unchanged.

## Python

Install the optional research stack explicitly with:

    pip install -e '.[phase1-nlp]'

The extra contains textacy, YAKE, KeyBERT, HDBSCAN, UMAP, scikit-network and ruptures. The helper module src/laclaugpt_data_analysis/analysis/phase1_baselines.py lazy-imports textacy, YAKE and KeyBERT only when requested.

KeyBERT requires a caller-supplied model and textacy requires a caller-prepared spaCy Doc. This prevents implicit model downloads. Returned keyword candidates are marked DESCRIPTIVE_ONLY. Keywords, clusters, similarity and centrality are not automatically Laclaudian signifiers, equivalence relations, ideological formations or hegemonic positions.

## DATS convergence

UHH-LT DATS (https://github.com/uhh-lt/dats) is a useful reference implementation for multimodal discourse analysis and already uses several compatible scientific libraries, including SentenceTransformers, HDBSCAN, UMAP, NetworkX, scikit-learn, Transformers and YAKE.

LaclauGPT selectively reuses these generic scientific building blocks while retaining its own canonical record, evidence/provenance model, plugin architecture and discourse-theoretical interpretation layer. DATS is a reference and interoperability target, not a runtime dependency.

## DNA and rDNA

The existing adapter at laclaugpt_data_analysis.interoperability.dna remains the canonical bridge to Discourse Network Analyzer (https://github.com/leifeld-lab/dna). It supports native .dna and transparent CSV interchange while preserving source URLs, actor/concept identities, stance, time, evidence, coder provenance and review status.

scripts/r/rdna_interop.R preserves the transparent statement table for rDNA workflows. DNA/rDNA outputs remain descriptive unless a separately validated inferential design supports stronger claims.

## R

R is an external reproducibility/interoperability layer and never a Python runtime dependency. Existing scripts cover quanteda, STM, rDNA-compatible statement exchange and igraph diagnostics. scripts/r/renv.lock provides a minimal environment scaffold; researchers should snapshot exact package versions for publication-facing runs.

All real derived files belong under ignored data/ paths.
