# Versioned analysis pipelines (#399)

The AI26 pipeline remains in this repository. The **complete original upstream repositories** are pinned as Git submodules, NOT rewritten as scientific aliases:

| ID | Path | Upstream ref | Source commit |
| --- | --- | --- | --- |
| ai26 | repository root | Data-Analysis main | current checkout |
| ep24 | external/ep24-current | Multimodal-Analysis main | db123759fe21b194275d87d6ccc3b7c4f98a2055 |
| ep24-legacy | external/ep24-legacy | Multimodal-Analysis legacy | e011c34274c41923e801c32c824c5afa7468e1a1 |

Submodules are pinned to immutable commits by Git gitlinks. Ordinary checkout without `--recursive` does not populate them; to initialize:

```bash
git clone --recurse-submodules https://github.com/TomiToivio/LaclauGPT-Data-Analysis.git
# or, in an existing checkout:
git submodule update --init --recursive
python scripts/analysis_pipeline.py list
python scripts/analysis_pipeline.py verify --pipeline ep24
python scripts/analysis_pipeline.py verify --pipeline ep24-legacy
```

Current EP24 is the original numbered Roihu pipeline, not AI26:

```bash
# Use only after configuring a private input root, per-stage environments, credentials and CSC account.
python scripts/analysis_pipeline.py run --pipeline ep24 -- --test
```

The legacy source has five distinct historical Puhti scripts. Run an individual step only with its historical environment and private inputs:

```bash
python scripts/analysis_pipeline.py run --pipeline ep24-legacy --step preprocess -- --help
```

**Safety:** The wrapper does not modify the canonical AI26 production runner. Legacy scripts predate the distributed AI26 record contract; do not assume Redis queue isolation, durable idempotency, or MongoDB result compatibility. Run historical workloads in an isolated environment and separate private input/output directories. Current EP24 Roihu scripts also need cluster-specific modules, model weights, Allas/MongoDB/Redis configuration and private datasets. Never point older pipelines at active AI26 production output keys.

**Status:** Source snapshots and a basic version selector are available. This is not proof of successfully executing all EP24 scientific stages on Roihu or legacy Puhti. Missing acceptance work: automated output namespacing across every version; schema adapters; full offline and live end-to-end regression; per-version run manifest and safe compare tool; CI submodule checkout tests. Keep issue #399 open until those are verified. See upstream licenses in each submodule.
