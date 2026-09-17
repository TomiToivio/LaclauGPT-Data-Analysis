"""Compatibility adapter for timecoded multimodal rhetoric-performative analysis."""
from __future__ import annotations

from typing import Any, Mapping

from ..canonical import CanonicalRecord
from ..plugin_pipeline import PluginContext, PluginSpec


class MultimodalRhetoricPerformativePlugin:
    """Package existing timecoded multimodal annotations under the shared method contract.

    This adapter does not generate rhetorical interpretations. It exposes frame/ASR/OCR
    evidence and any already-produced frame-analysis annotations for human/model-assisted
    theoretical interpretation downstream.
    """

    spec = PluginSpec(
        name="acdt_multimodal_rhetoric_performative",
        version="1.0",
        method_id="multimodal_rhetoric_performative",
        method_version="1.0",
        interpretation_mode="theoretical_interpretive",
        scope="record",
        requires=frozenset({"canonical_record"}),
        produces=frozenset({"multimodal_rhetoric_performative"}),
        deterministic=True,
    )

    def process(
        self,
        record: CanonicalRecord,
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context, config
        transcripts = [item.model_dump(mode="json") for item in record.content.transcripts]
        ocr = [item.model_dump(mode="json") for item in record.content.ocr]
        frames = [item.model_dump(mode="json") for item in record.content.frames]
        annotations = list(record.intermediate.frame_analysis)
        timecodes = sorted(
            {
                float(item["timestamp_seconds"])
                for item in [*ocr, *frames, *annotations]
                if isinstance(item, Mapping) and item.get("timestamp_seconds") is not None
            }
        )
        return {
            "transcript": transcripts,
            "ocr": ocr,
            "frames": frames,
            "frame_analysis": annotations,
            "timecodes_seconds": timecodes,
            "evidence_record_ids": [record.source_url],
            "semantic_status": "existing_annotations_exposed_without_new_theoretical_inference",
        }
