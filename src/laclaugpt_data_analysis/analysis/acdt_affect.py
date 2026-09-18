"""Validated lexicon-based AC/DT sentiment, emotion and intensity plugins.

These are deliberately auxiliary measurement plugins. They never emit Laclaudian
affective-investment, antagonism or hegemony codes. Researchers must provide explicit
lexicon identity, language and validation metadata.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Mapping

from ..canonical import CanonicalRecord
from ..plugin_pipeline import PluginContext, PluginSpec

_TOKEN = re.compile(r"\b[^\W\d_][\w'’-]*\b", re.UNICODE)
_ALLOWED_VALIDATION = {"partial", "validated"}


class ValidatedLexiconAffectPlugin:
    def __init__(self, mode: str) -> None:
        if mode not in {"sentiment", "emotion", "emotion_intensity"}:
            raise ValueError(f"unsupported affect mode: {mode}")
        self.mode = mode
        method_id = {
            "sentiment": "sentiment_analysis",
            "emotion": "emotion_analysis",
            "emotion_intensity": "emotion_intensity",
        }[mode]
        self.spec = PluginSpec(
            name=f"acdt_{mode}",
            phase=2, default_enabled=False, experimental=True,
            version="1.0",
            method_id=method_id,
            method_version="1.0",
            interpretation_mode="measurement",
            scope="record",
            requires=frozenset({"text"}),
            produces=frozenset({method_id}),
            deterministic=True,
        )

    @staticmethod
    def _metadata(config: Mapping[str, Any]) -> tuple[str, str, str]:
        language = str(config.get("language") or "").strip()
        lexicon_id = str(config.get("lexicon_id") or "").strip()
        validation = str(config.get("lexicon_validation") or "").strip().lower()
        if not language:
            raise ValueError("language is required for validated lexicon analysis")
        if not lexicon_id:
            raise ValueError("lexicon_id is required for validated lexicon analysis")
        if validation not in _ALLOWED_VALIDATION:
            raise ValueError("lexicon_validation must be 'partial' or 'validated'")
        return language, lexicon_id, validation

    def process(
        self,
        record: CanonicalRecord,
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context
        language, lexicon_id, validation = self._metadata(config)
        source_language = record.source.language or record.content.language or ""
        if source_language and source_language != language and not record.content.translated_text:
            raise ValueError(
                f"record language {source_language!r} differs from lexicon language {language!r}; "
                "provide translated text or a language-matched lexicon"
            )
        text = record.content.translated_text or record.content.text
        tokens = [match.group(0).casefold() for match in _TOKEN.finditer(text)]
        lexicon = config.get("lexicon")
        if not isinstance(lexicon, Mapping):
            raise ValueError("lexicon must be a mapping")

        if self.mode == "sentiment":
            scores: list[float] = []
            labels: Counter[str] = Counter()
            for token in tokens:
                value = lexicon.get(token)
                if isinstance(value, (int, float)):
                    scores.append(float(value))
                elif isinstance(value, str):
                    labels[value] += 1
            output: dict[str, Any] = {
                "matched_tokens": len(scores) + sum(labels.values()),
                "mean_score": (sum(scores) / len(scores)) if scores else None,
                "label_counts": dict(labels),
            }
        elif self.mode == "emotion":
            emotions: Counter[str] = Counter()
            for token in tokens:
                value = lexicon.get(token)
                if isinstance(value, str):
                    emotions[value] += 1
                elif isinstance(value, (list, tuple, set)):
                    emotions.update(str(item) for item in value)
                elif isinstance(value, Mapping):
                    emotions.update(str(key) for key, flag in value.items() if flag)
            output = {"emotion_counts": dict(emotions), "matched_tokens": sum(emotions.values())}
        else:
            totals: Counter[str] = Counter()
            matches: Counter[str] = Counter()
            for token in tokens:
                value = lexicon.get(token)
                if isinstance(value, (int, float)):
                    totals["overall"] += float(value)
                    matches["overall"] += 1
                elif isinstance(value, Mapping):
                    for emotion, intensity in value.items():
                        if isinstance(intensity, (int, float)):
                            totals[str(emotion)] += float(intensity)
                            matches[str(emotion)] += 1
            output = {
                "mean_intensity": {
                    emotion: totals[emotion] / matches[emotion]
                    for emotion in sorted(matches)
                    if matches[emotion]
                },
                "matched_tokens": dict(matches),
            }

        output.update(
            {
                "lexicon_id": lexicon_id,
                "lexicon_language": language,
                "lexicon_validation": validation,
                "source_language": source_language or None,
                "translated": bool(record.content.translated_text),
                "semantic_status": "auxiliary_measurement_not_affective_investment",
            }
        )
        return output
