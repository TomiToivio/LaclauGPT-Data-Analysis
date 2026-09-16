# Plugin pipeline architecture

LaclauGPT Data Analysis uses a stable three-stage architecture:

```text
RAW / CANONICAL INPUT
        |
        v
PREPROCESS
(generic normalization / representation assembly)
        |
        v
PLUGIN -> PLUGIN -> ... -> PLUGIN
(arbitrary analytical methods)
        |
        v
POSTPROCESS
(generic validation / projection / export)
        |
        +--> canonical JSON / MongoDB
        +--> CSV / dataframe views
        +--> graphs / sidecars
        +--> visualization / reports / RAG
```

The “WordPress for social data science” phrase is a modularity metaphor. Collection, Analysis and Visualization remain independently deployable modules. This document concerns the internal extensibility of **Data Analysis**.

## Design rule

> Preprocess once, analyze through any number of composable methods, postprocess once.

The core does not assume that a workflow contains Laclau analysis, populism, an LLM, multimodal data, or even a per-document method.

## Canonical record

The existing `CanonicalRecord` remains the shared record contract. Raw capture, normalized content, intermediate products, evidence, provenance, review state and legacy projections are preserved. Generic plugin output is collision-safe:

```json
{
  "analysis": {
    "plugin_results": {
      "sentiment": {"plugin_version": "1.0", "output": {}},
      "laclau": {"plugin_version": "1.0", "output": {}}
    },
    "plugin_failures": {}
  }
}
```

Selected stable/common analytical fields can continue to exist in the canonical schema for interoperability. Arbitrary method-specific output belongs under `plugin_results`.

## Preprocess versus analytical framing

`Preprocessor` performs generic representation work only. Examples include assembling already extracted transcript/OCR text, exposing capabilities, and preserving intermediate outputs. Generic image/frame description therefore belongs in preprocess.

Political/media **framing analysis** is a substantive analytical method and belongs in the plugin stage.

This boundary prevents preprocessing from silently encoding one theory of politics.

## Plugin contract

Plugins expose a versioned `PluginSpec` and either a record or corpus method.

```python
from laclaugpt_data_analysis.plugin_pipeline import PluginSpec

class SentimentPlugin:
    spec = PluginSpec(
        name="sentiment",
        version="1.0",
        scope="record",
        requires=frozenset({"text"}),
        produces=frozenset({"sentiment"}),
        deterministic=False,
        model_dependencies=("my-model",),
    )

    def process(self, record, context, config):
        return {"label": "neutral", "score": 0.7}
```

A plugin declares:

- unique name and version;
- scope: `record` or `corpus`;
- required capabilities;
- produced capabilities;
- optional dependencies on earlier plugins;
- deterministic/non-deterministic status;
- model dependencies;
- config schema version.

The result envelope automatically retains plugin/version/config hash/run/worker/review metadata.

## Corpus plugins

Corpus/graph methods use the same specification but implement `process_corpus(records, context, config)`. Their outputs are postprocess sidecars rather than being copied into every source record.

Suitable corpus plugins include DNA projections, SNA metrics, Bourdieu MCA/GDA, topic models and temporal change analysis.

## Registry and external plugins

First-party plugins can be registered directly:

```python
registry = PluginRegistry()
registry.register(SentimentPlugin())
```

External packages may expose Python entry points in the group:

```text
laclaugpt.analysis_plugins
```

Then `PluginRegistry.discover()` loads them using standard Python packaging. This permits future packages such as `laclaugpt-plugin-dna` without requiring them now.

## Dependencies and ordering

The user-facing pipeline is an ordered chain. A plugin may declare dependencies that must appear earlier. The first implementation intentionally executes the configured record chain sequentially. The capability/dependency interface leaves room for a future DAG scheduler without changing plugin APIs.

Missing capabilities are recorded as clear plugin failures by default. `fail_fast=True` can turn these into immediate exceptions.

## Failure isolation

One plugin failure does not erase raw data or successful outputs from other plugins. Failures are namespaced in `analysis.plugin_failures`; successful later plugins can continue unless `fail_fast=True`.

Plugins receive deep copies of records and return additive result mappings. The core protects canonical `source_url` identity from replacement.

## Laclau as a plugin

`LegacyLaclauPlugin` adapts the existing canonical Laclau workflow to the generic contract. The actual executor is injected so the plugin core remains independent of providers, prompts and models.

Typical wrapper:

```python
def laclau_executor(record, config):
    return run_canonical_pipeline(
        record,
        provider=provider,
        context=pipeline_context,
        codebook_entries=codebook.entries,
        model=model,
        project_profile=profile,
    )

registry.register(LegacyLaclauPlugin(laclau_executor))
```

The legacy analysis then appears under `analysis.plugin_results["laclau"]` while the old canonical fields remain available to existing code during migration.

## Example pipeline A: discourse research

Equivalent configuration concept:

```yaml
preprocess:
  preserve_raw: true
  multimodal: auto

process:
  plugins:
    - name: claims
    - name: framing
    - name: laclau
      config:
        codebook: codebooks/laclau.yaml
    - name: discourse_network_analysis

postprocess:
  outputs: [canonical, csv, mongodb, graph, human_summary]
```

The core does not know what “claims”, “framing” or “laclau” mean. Their contracts define what they require and produce.

## Example pipeline B: event/geospatial monitoring

```yaml
process:
  plugins:
    - name: sentiment
    - name: events
    - name: geospatial
    - name: temporal_aggregation
```

The same preprocess and postprocess stages work without Laclau, framing or populism semantics.

## Existing methods

Luhmann, Castells/SNA, Bourdieu/GDA, DNA, topic modelling and other first-party methods should migrate through adapters rather than becoming bespoke top-level pipelines. Existing implementations do not need to be rewritten all at once.

## Postprocess contract

`Postprocessor` validates canonical records and gives stable status semantics independent of plugin selection:

- `preprocessed`: no analytical plugin output;
- `analysis-complete`: plugin outputs exist and no plugin failed;
- `analysis-partial`: at least one plugin failed or lacked required capabilities.

`PipelineResult.flat_rows()` provides a conservative dataframe projection with plugin results kept as JSON rather than flattening unknown schemas into collision-prone columns. More specialized CSV/Parquet/Mongo/graph exporters can consume the same result object.

## Provenance

For each successful record plugin, the record receives analysis provenance including plugin name/version, config hash and run ID. Result envelopes also carry config/codebook revisions when supplied in `PluginContext`.

This keeps distributed execution reproducible while allowing Redis/config pinning to remain an orchestration concern rather than a substantive-method concern.

## Migration guidance

1. Keep current method implementation intact.
2. Add a small adapter exposing `PluginSpec` plus `process` or `process_corpus`.
3. Declare actual input capabilities and method dependencies.
4. Return method-specific output rather than replacing raw/canonical state.
5. Register the adapter in a project registry.
6. Gradually move consumers from bespoke top-level fields to namespaced plugin output where appropriate.

Do not collapse Collection, Analysis and Visualization into one process while doing this migration.
