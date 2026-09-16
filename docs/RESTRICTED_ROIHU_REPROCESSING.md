# Restricted-project reprocessing on CSC Roihu

This workflow is for official/restricted projects such as EP24 Finland, EP24 Poland and Hungary26. It intentionally differs from the public AI26 example: the public repository contains only the generic engine, schemas and templates. Real manifests, object references, source/account lists, codebooks, CSC paths, MongoDB/Redis endpoints, Allas bucket names and researcher outputs stay in private runtime configuration or private repositories.

## Private-asset audit

The implementation was designed after auditing the existing private EP24/Hungary26 assets rather than replacing them blindly.

Useful private EP24 behavior retained as generic architecture:

- Roihu GPU jobs use an ARM64 environment built on Roihu itself;
- the known working module stack is `gcc/14.3.0`, `python-pytorch/2.13`, and `ffmpeg`;
- local Ollama uses a job-specific port to avoid collisions between jobs sharing a node;
- persistent model/runtime caches survive Slurm jobs;
- country-specific human codebooks are fail-closed private inputs;
- original media is fetched before multimodal processing;
- transcript, OCR/frame analysis, legacy intermediate fields, canonical analysis and human-readable researcher exports are all retained rather than collapsing to final labels.

The old private EP24 pilot is intentionally not copied verbatim because it embeds official-project paths/account details and private seed/codebook locations. Hungary26 is already project-config driven, so the public engine keeps project differences in private bindings instead of creating a third pipeline.

## Public/private split

Public reusable pieces:

```text
src/laclaugpt_data_analysis/reprocessing.py
config/examples/roihu_reprocessing.example.yaml
scripts/roihu/run_reprocessing.sh
scripts/roihu/reprocess_project.sbatch
```

Private project binding, one per dataset:

```text
project_id: ep24_finland | ep24_poland | hungary26
manifest: <private canonical JSONL manifest>
codebook: <private validated YAML/JSON codebook>
preprocessor_hook: <optional private module:function>
```

The private manifest consists of canonical LaclauGPT records. A protected Allas object reference may be supplied at the configured `source_object_field`, by default `source.raw_metadata.object_ref`, with an optional SHA-256 at `source.raw_metadata.sha256`.

## Pipeline

```text
private canonical manifest
  -> protected Allas/S3 object staging
  -> checksum validation
  -> optional private multimodal preprocessor hook
       -> ASR / Whisper
       -> OCR / frames / frame observations
       -> translations
       -> legacy intermediate fields
  -> canonical LaclauGPT pipeline
  -> private project codebook
  -> MongoDB durable enriched record
  -> Redis best-effort lease/progress marker
  -> atomic CSV checkpoint
  -> optional protected Allas checkpoint archive
  -> researcher-facing human summary retained in canonical record
```

The private `preprocessor_hook` must use the public `Preprocessor` contract from `canonical_pipeline.py`: it receives a `CanonicalRecord` and may return keys such as `asr`, `ocr`, `frames`, `translations`, `legacy`, and `stage_output`. This is the seam for adapting the existing EP24 multimodal implementation without copying protected project code into the public repository.

## Environment

Install with the required optional adapters:

```bash
python -m pip install -e '.[analysis,nlp,ollama,remote]'
```

The official Roihu profile should provide, through private environment/configuration, at least:

```text
LACLAUGPT_PROJECT_ID
LACLAUGPT_DATA_DIR
LACLAUGPT_STORAGE=distributed
LACLAUGPT_STORAGE_BACKEND=mongodb
LACLAUGPT_MONGODB_URI
LACLAUGPT_MONGO_DATABASE
LACLAUGPT_CACHE_BACKEND=redis
LACLAUGPT_REDIS_URL
LACLAUGPT_OBJECT_BACKEND=s3
LACLAUGPT_S3_ENDPOINT
LACLAUGPT_S3_BUCKET
LACLAUGPT_S3_REGION
LACLAUGPT_S3_PREFIX_ROOT
```

Do not put these values in tracked Slurm files.

## Dry run

A dry run validates the project binding, manifest and codebook without starting analysis:

```bash
laclaugpt-reprocess --config data/config/restricted/project.yaml --dry-run
```

The runtime `LACLAUGPT_PROJECT_ID` must equal the private config `project_id`.

## Full or sharded execution

Full private manifest:

```bash
bash scripts/roihu/run_reprocessing.sh data/config/restricted/project.yaml
```

Bounded shard/range:

```bash
bash scripts/roihu/run_reprocessing.sh data/config/restricted/project.yaml 0 250
bash scripts/roihu/run_reprocessing.sh data/config/restricted/project.yaml 250 500
```

The generic Slurm template is submitted through a private wrapper that supplies the CSC account, repository path, virtualenv, private config and secrets:

```bash
sbatch scripts/roihu/reprocess_project.sbatch
```

For large corpora, private wrappers may use arrays by assigning non-overlapping `REPROCESS_START` / `REPROCESS_STOP` ranges. Redis lease timestamps reduce concurrent duplicate work; MongoDB analysis status remains the durable source for completed work, so loss of Redis does not erase completion state.

## Checkpoints and resume

Checkpoints are written atomically under:

```text
data/csv/<project_id>/checkpoints/
```

Each row includes:

- canonical `source_url`;
- analysis status;
- human-readable summary;
- complete canonical record as deterministic JSON;
- explicit legacy/intermediate/provenance JSON columns.

Writes use a temporary file followed by `os.replace`, keep rotating snapshots plus `latest.csv`, and can be archived to protected Allas/S3. The checkpoint interval and retention are configured privately. MongoDB remains primary durable structured state; checkpoints are recovery/researcher exports, not a competing schema.

Re-running without `--force` skips records already durably marked analyzed. Stale Redis leases expire logically after the configured lease timeout. Failed records retain an error in reprocessing metadata and can be retried later.

## EP24 Finland / Poland binding

The private EP24 binding should adapt the existing private multimodal behavior through `preprocessor_hook`, including media staging, ASR, frame extraction/OCR/vision, translation where applicable, and legacy dataframe fields. The real Finland/Poland human codebooks and seed manifests remain private and should be referenced by path, never copied into this repository.

## Hungary26 binding

Hungary26 should use the same public engine with a private Hungarian project codebook/config and a multimodal preprocessor hook where media analysis is enabled. The public engine does not hard-code the country's analysis switches or targets.

## Validation checklist

Before a full official run:

1. private manifest and codebook validate;
2. one public-safe/synthetic or approved protected object stages from Allas and passes checksum validation;
3. the private preprocessor produces transcript/frame/legacy structures expected by the canonical pipeline;
4. one enriched record upserts to MongoDB;
5. Redis status/lease operation succeeds but processing still has durable Mongo/checkpoint state;
6. an atomic checkpoint is written and, when enabled, archived to Allas;
7. rerunning skips the completed item;
8. a failed item records an error and becomes retryable after lease expiry or with `--force`;
9. no credentials, object names, source lists, official project paths or private codebooks appear in Git or logs.

## Privacy

Treat `.dna`, CSV/JSONL outputs, manifests, media, codebooks and generated reports as research/runtime data. The complete `data/` tree remains ignored. Public tests must use synthetic records and mocked/local adapters only.
