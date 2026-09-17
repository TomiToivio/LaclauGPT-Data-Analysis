# AC/DT backwards compatibility

This repository implements the analysis side of `TomiToivio/LaclauGPT#36`.

The shared stable IDs and result schema are defined in the core repository:

- `schemas/acdt_method_registry.v1.yaml`
- `schemas/acdt_result.v1.schema.json`
- `docs/ACDT_METHOD_CONTRACT.md`

## Result envelope

Every plugin result emitted by `AnalysisPipeline` now includes:

- `schema_version = acdt-result/1.0`
- stable `method_id` and `method_version`
- `interpretation_mode`
- study/corpus/input record IDs
- parameters/config provenance
- producer/run metadata
- validation + human-review state
- the original plugin metadata for backwards compatibility

Plugin software names are deliberately distinct from stable research method IDs.

## Interpretation modes

`exploratory_instrumentalist` means a computational structure is used for navigation, discovery, sampling or close reading. `measurement` means the output is treated as a measurement and therefore needs method-specific validation. `theoretical_interpretive` means a theory-bearing interpretation that must remain evidence-linked and human-reviewable.

## Implemented compatibility plugins

`src/laclaugpt_data_analysis/analysis/acdt_compat.py` provides dependency-light first-party implementations/adapters for:

- `word_frequency`
- `hashtag_cooccurrence`
- `peak_analysis` with legacy absolute-count threshold support
- `close_reading_sampler` with random/actor/peak/event/topic/outlier/validation modes
- `topic_model_lda` / `topic_model_generic` executor adapters for existing topic backends
- pass-through adapters for imported legacy `wordscores`, `wordfish`, sentiment, emotion and emotion-intensity measurements

The network plugin emits `cooccurrence_candidate`, not a Laclaudian articulation. Topic adapters explicitly emit `topic_is_not_frame_discourse_or_ideology`. Measurement adapters explicitly remain measurements.

## Registration example

```python
from laclaugpt_data_analysis.analysis.acdt_compat import first_party_acdt_plugins
from laclaugpt_data_analysis.plugin_pipeline import PluginRegistry

registry = PluginRegistry()
for plugin in first_party_acdt_plugins():
    registry.register(plugin)
```

Existing BERTopic/Gensim/scikit-learn backends can be wrapped with `TopicModelAdapterPlugin` rather than reimplemented.

## Semantic safeguards

Compatibility does not weaken `THEORY.md`: frequency is not hegemony, co-occurrence is not articulation, network communities are not ideological formations, sentiment/emotion are not affective investment, and topic membership is not a discourse/frame/ideology classification.

`tests/test_acdt_compat.py` verifies stable envelopes, evidence drill-down, reproducible close-reading sampling and these semantic barriers.