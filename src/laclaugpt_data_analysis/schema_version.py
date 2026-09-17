from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .canonical import (
    SCHEMA_VERSION,
    CanonicalRecord,
    HumanReadableSection,
    IntermediateSection,
    RawCaptureSection,
)


class UnsupportedSchemaVersion(ValueError):
    pass


def _adapt_shared_parity_fixture(data: dict[str, Any]) -> dict[str, Any]:
    """Map the public cross-module parity fixture into the Analysis canonical model.

    The shared fixture is deliberately module-neutral and slightly richer than the
    Analysis model. Preserve every normative invariant while storing fixture-only
    fields losslessly in canonical namespaces that survive all local adapters.
    """
    source = dict(data.get("source") or {})
    content = dict(data.get("content") or {})
    analysis = dict(data.get("analysis") or {})
    review = dict(data.get("review") or {})

    # Cross-module multimodal field names are normalized to the Analysis model.
    transcripts = []
    for index, item in enumerate(content.get("transcripts") or [], start=1):
        value = dict(item)
        value.setdefault("id", f"transcript_{index}")
        transcripts.append(value)
    content["transcripts"] = transcripts

    ocr = []
    for index, item in enumerate(content.get("ocr") or [], start=1):
        value = dict(item)
        value.setdefault("id", f"ocr_{index}")
        if "frame_timestamp_seconds" in value and "timestamp_seconds" not in value:
            value["timestamp_seconds"] = value.pop("frame_timestamp_seconds")
        ocr.append(value)
    content["ocr"] = ocr

    frames = []
    for index, item in enumerate(content.get("frames") or [], start=1):
        value = dict(item)
        value.setdefault("id", f"frame_{index}")
        if "frame_timestamp_seconds" in value and "timestamp_seconds" not in value:
            value["timestamp_seconds"] = value.pop("frame_timestamp_seconds")
        frames.append(value)
    content["frames"] = frames

    media = []
    for item in content.get("media_references") or []:
        value = dict(item)
        if "media_type" in value and "kind" not in value:
            value["kind"] = value.pop("media_type")
        if "ref" in value and "object_ref" not in value:
            value["object_ref"] = value.pop("ref")
        value.setdefault("url", "")
        media.append(value)
    content["media_references"] = media

    # Preserve module-neutral analytical objects in the collision-safe plugin area.
    shared_plugin = dict((analysis.get("plugin_results") or {}).get("cross_module_fixture") or {})
    for key in ("analysis_objects", "events", "actors", "narrative_episodes"):
        if key in analysis:
            shared_plugin[key] = analysis.pop(key)
    if shared_plugin:
        analysis.setdefault("plugin_results", {})["cross_module_fixture"] = shared_plugin

    # Convert simple shared vocabulary forms to Analysis discourse objects without
    # inventing evidentiary claims. Original shared forms remain in plugin_results.
    for key, kind in (
        ("formations", "formation"),
        ("signifiers", "signifier"),
        ("nodal_points", "nodal_point"),
        ("discourses", "discourse"),
        ("imaginaries", "imaginary"),
        ("us", "us"),
        ("them", "them"),
        ("frontier", "frontier"),
        ("affects", "affect"),
        ("sentiments", "sentiment"),
    ):
        values = analysis.get(key) or []
        normalized = []
        for index, item in enumerate(values, start=1):
            if isinstance(item, str):
                normalized.append({"object_id": f"fixture_{key}_{index}", "label": item, "kind": kind})
            elif isinstance(item, Mapping):
                value = dict(item)
                value.setdefault("object_id", str(value.pop("id", f"fixture_{key}_{index}")))
                value.setdefault("kind", kind)
                normalized.append(value)
        analysis[key] = normalized

    # Topics in the shared fixture may be labels rather than full topic records.
    topics = []
    for index, item in enumerate(analysis.get("topics") or [], start=1):
        if isinstance(item, str):
            topics.append({"topic_id": f"fixture_topic_{index}", "canonical_label": item})
        else:
            topics.append(item)
    analysis["topics"] = topics

    # Analysis keeps flexible provenance/reference details losslessly in JSON objects.
    analysis["codebook_refs"] = [
        item if isinstance(item, str) else "@".join(
            part for part in (str(item.get("id", "")), str(item.get("version", ""))) if part
        )
        for item in analysis.get("codebook_refs") or []
    ]
    analysis["uncertainty"] = [
        item if isinstance(item, str) else __import__("json").dumps(item, sort_keys=True)
        for item in analysis.get("uncertainty") or []
    ]

    # Shared evidence edges use graph terminology; preserve their full shape in metadata.
    evidence = []
    for item in data.get("evidence") or []:
        value = dict(item)
        evidence.append(
            {
                "evidence_id": value.get("evidence_id", "fixture_evidence"),
                "kind": value.get("relation", value.get("kind", "derived_from")),
                "source_url": value.get("source_url", data.get("source_url", "")),
                "provenance_id": value.get("provenance_id", ""),
                "metadata": value,
            }
        )

    # Preserve source units/alignments/review events as lossless legacy extension data.
    legacy = dict(data.get("legacy") or {})
    for key in ("fixture_version", "source_units", "alignments"):
        if key in data:
            legacy[f"cross_module_{key}"] = data.get(key)
    if "review_events" in review:
        legacy["cross_module_review_events"] = review.pop("review_events")

    # Keep raw reference reachable in both historical and current canonical layers.
    raw_ref = source.get("raw_ref")
    data.setdefault(
        "raw_capture",
        RawCaptureSection(
            ref=str(raw_ref) if raw_ref else None,
            metadata={"preservation": "cross-module-parity-fixture"},
        ).model_dump(mode="python"),
    )
    data.setdefault("intermediate", IntermediateSection().model_dump(mode="python"))
    data.setdefault("human_readable", HumanReadableSection().model_dump(mode="python"))
    data["source"] = source
    data["content"] = content
    data["analysis"] = analysis
    data["review"] = review
    data["evidence"] = evidence
    data["legacy"] = legacy
    data.pop("fixture_version", None)
    data.pop("source_units", None)
    data.pop("alignments", None)
    return data


def normalize_schema_version(payload: Mapping[str, Any]) -> CanonicalRecord:
    """Normalize supported historical records to the current four-layer contract."""
    data = dict(payload)
    version = str(data.get("schema_version") or "")
    if version == "1.1.0-draft" and data.get("fixture_version"):
        data = _adapt_shared_parity_fixture(data)
        data["schema_version"] = SCHEMA_VERSION
    elif version in {"1.0", "1.0.0"}:
        source = dict(data.get("source") or {})
        content = dict(data.get("content") or {})
        raw_ref = source.get("raw_ref")
        data.setdefault(
            "raw_capture",
            RawCaptureSection(
                ref=str(raw_ref) if raw_ref else None,
                metadata={
                    "preservation": (
                        "legacy-durable-reference" if raw_ref else "compatibility-missing-original"
                    )
                },
            ).model_dump(mode="python"),
        )
        data.setdefault("intermediate", IntermediateSection().model_dump(mode="python"))
        preview = str(content.get("text") or "")
        data.setdefault(
            "human_readable",
            HumanReadableSection(
                summary=preview[:500],
                markdown=(
                    f"# Research record\n\n## Collected content\n{preview[:2000]}"
                    if preview
                    else "# Research record"
                ),
                generator="laclaugpt-data-analysis/schema-migration",
                sections={"content": preview[:2000]},
            ).model_dump(mode="python"),
        )
        data["schema_version"] = SCHEMA_VERSION
    elif version in {"1.1", "1.1.0"}:
        data["schema_version"] = SCHEMA_VERSION
    elif version != SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(
            f"unsupported schema version {version!r}; expected {SCHEMA_VERSION!r}"
        )
    return CanonicalRecord.model_validate(data)
