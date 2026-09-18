from __future__ import annotations

import json
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

    The fixture remains the normative contract. Analysis normalizes its richer neutral
    shapes into local strict models while preserving the original values losslessly in
    canonical extension namespaces that survive every supported local adapter.
    """
    source = dict(data.get("source") or {})
    content = dict(data.get("content") or {})
    analysis = dict(data.get("analysis") or {})
    review = dict(data.get("review") or {})
    legacy = dict(data.get("legacy") or {})

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
        # Preserve the neutral names *and* populate the local aliases. Popping them
        # lost the original value whenever only one spelling was present (#75).
        if "media_type" in value and "kind" not in value:
            value["kind"] = value["media_type"]
        if "ref" in value and "object_ref" not in value:
            value["object_ref"] = value["ref"]
        value.setdefault("url", "")
        media.append(value)
    content["media_references"] = media

    shared_plugin = dict((analysis.get("plugin_results") or {}).get("cross_module_fixture") or {})
    for key in ("analysis_objects", "events", "actors", "narrative_episodes"):
        if key in analysis:
            shared_plugin[key] = analysis.pop(key)

    original_codebook_refs = list(analysis.get("codebook_refs") or [])
    original_uncertainty = list(analysis.get("uncertainty") or [])
    shared_plugin["codebook_refs"] = original_codebook_refs
    shared_plugin["uncertainty"] = original_uncertainty
    analysis.setdefault("plugin_results", {})["cross_module_fixture"] = shared_plugin

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
                normalized.append(
                    {"object_id": f"fixture_{key}_{index}", "label": item, "kind": kind}
                )
            elif isinstance(item, Mapping):
                value = dict(item)
                value.setdefault("object_id", str(value.pop("id", f"fixture_{key}_{index}")))
                value.setdefault("kind", kind)
                normalized.append(value)
        analysis[key] = normalized

    entities = []
    for item in analysis.get("entities") or []:
        if isinstance(item, Mapping):
            value = dict(item)
            if "type" in value and "entity_type" not in value:
                value["entity_type"] = value.pop("type")
            entities.append(value)
        else:
            entities.append(item)
    analysis["entities"] = entities

    topics = []
    for index, item in enumerate(analysis.get("topics") or [], start=1):
        if isinstance(item, str):
            topics.append({"topic_id": f"fixture_topic_{index}", "canonical_label": item})
        else:
            topics.append(item)
    analysis["topics"] = topics

    analysis["codebook_refs"] = [
        item
        if isinstance(item, str)
        else "@".join(
            part
            for part in (str(item.get("id", "")), str(item.get("version", "")))
            if part
        )
        for item in original_codebook_refs
    ]
    analysis["uncertainty"] = [
        item if isinstance(item, str) else json.dumps(item, sort_keys=True)
        for item in original_uncertainty
    ]

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

    for key in ("fixture_version", "source_units", "alignments"):
        if key in data:
            legacy[f"cross_module_{key}"] = data.get(key)
    if "review_events" in review:
        legacy["cross_module_review_events"] = review.pop("review_events")

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
