"""Legacy political-text scaling adapters for AC/DT compatibility.

The adapters can wrap a real Wordscores/Wordfish executor or expose imported legacy
measurements. They require an explicit scaling dimension and preserve validation metadata.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from ..canonical import CanonicalRecord
from ..plugin_pipeline import PluginContext, PluginSpec

ScalingExecutor = Callable[[Sequence[CanonicalRecord], Mapping[str, Any]], Mapping[str, Any]]


class LegacyScalingPlugin:
    def __init__(self, method_id: str, executor: ScalingExecutor | None = None) -> None:
        if method_id not in {"wordscores", "wordfish"}:
            raise ValueError("method_id must be 'wordscores' or 'wordfish'")
        self.method_id = method_id
        self.executor = executor
        self.spec = PluginSpec(
            name=f"acdt_{method_id}",
            version="1.0",
            method_id=method_id,
            method_version="1.0",
            interpretation_mode="measurement",
            scope="corpus",
            requires=frozenset({"corpus", "text"}),
            produces=frozenset({method_id}),
            deterministic=executor is None,
        )

    def process_corpus(
        self,
        records: Sequence[CanonicalRecord],
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context
        dimension = str(config.get("scaling_dimension") or "").strip()
        if not dimension:
            raise ValueError("scaling_dimension is required for Wordscores/Wordfish compatibility")

        validation = dict(config.get("validation") or {})
        preprocessing = dict(config.get("preprocessing") or {})
        if self.executor is not None:
            computed = dict(self.executor(records, config))
            values = computed.get("values", computed)
            diagnostics = dict(computed.get("diagnostics") or {})
            recomputed = True
        else:
            field = str(config.get("legacy_field") or f"{self.method_id}_position")
            values = []
            missing = []
            for record in records:
                original = record.legacy.get("original") if isinstance(record.legacy, dict) else None
                source = original if isinstance(original, dict) else {}
                if field in source:
                    values.append({"record_id": record.source_url, "value": source[field]})
                else:
                    missing.append(record.source_url)
            diagnostics = {
                "legacy_field": field,
                "records_with_value": len(values),
                "records_missing_value": len(missing),
                "missing_record_ids": missing,
            }
            recomputed = False

        return {
            "method": self.method_id,
            "scaling_dimension": dimension,
            "values": values,
            "diagnostics": diagnostics,
            "validation": validation,
            "preprocessing": preprocessing,
            "reference_texts": list(config.get("reference_texts", [])) if self.method_id == "wordscores" else [],
            "recomputed": recomputed,
            "semantic_status": "latent_scale_not_ideology_without_substantive_validation",
        }
