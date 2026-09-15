"""Hugging Face Transformers inference backend."""
from __future__ import annotations

from typing import Any

from . import BackendUnavailable
from ..models import ClassificationResult, Provenance

_BACKEND = "transformers"
_ENGINES: dict[str, Any] = {}


def is_available() -> bool:
    try:
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _version() -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version("transformers")
    except Exception:
        return ""


def _pipeline(task: str, model: str):
    if not is_available():
        raise BackendUnavailable("transformers is not installed")
    key = f"{task}:{model}"
    if key not in _ENGINES:
        from transformers import pipeline as hf_pipeline
        _ENGINES[key] = hf_pipeline(task=task, model=model)
    return _ENGINES[key]


def classify(
    text: str, *, task: str, model: str | None = None,
    provenance: Provenance | None = None, candidate_labels: list[str] | None = None,
) -> ClassificationResult:
    task_map = {
        "sentiment": "sentiment-analysis",
        "text_classification": "text-classification",
        "zero_shot": "zero-shot-classification",
        "ner": "token-classification",
        "emotion": "text-classification",
    }
    hf_task = task_map.get(task)
    if hf_task is None:
        raise ValueError(f"unknown transformers task: {task}")
    if model is None:
        raise ValueError(f"transformers task {task!r} requires an explicit configured model")
    engine = _pipeline(hf_task, model)
    if task == "zero_shot":
        if not candidate_labels:
            raise ValueError("zero_shot requires candidate_labels")
        output = engine(text, candidate_labels=candidate_labels)
        labels = output.get("labels") or []
        scores = output.get("scores") or []
        label = str(labels[0]) if labels else ""
        confidence = float(scores[0]) if scores else None
    else:
        output = engine(text)
        top = output[0] if isinstance(output, list) and output else output
        label = str(top.get("label", "")) if isinstance(top, dict) else ""
        confidence = float(top["score"]) if isinstance(top, dict) and top.get("score") is not None else None
    return ClassificationResult(
        label=label,
        confidence=confidence,
        task=task,
        model=model,
        model_version=_version(),
        backend=_BACKEND,
        provenance_id=provenance.provenance_id if provenance else "",
    )


def extract_mentions(text: str, *, model: str, provenance: Provenance | None = None) -> list[dict[str, Any]]:
    engine = _pipeline("token-classification", model)
    return [
        {
            "surface_form": entry.get("word", ""),
            "transformers_label": entry.get("entity_group") or entry.get("entity", ""),
            "start_offset": entry.get("start"),
            "end_offset": entry.get("end"),
            "confidence": float(entry.get("score") or 0.0),
            "model": model,
            "backend": _BACKEND,
            "provenance_id": provenance.provenance_id if provenance else "",
        }
        for entry in engine(text)
    ]
