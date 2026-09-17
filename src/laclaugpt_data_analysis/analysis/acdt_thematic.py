"""Evidence-linked thematic-analysis adapter for AC/DT compatibility.

The adapter provides a stable method identity for manual, rule-based or LLM-assisted
thematic analysis while keeping interpretation and evidence explicit. It does not infer
Laclaudian articulation, ideology or hegemony from a theme assignment.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from ..canonical import CanonicalRecord
from ..plugin_pipeline import PluginContext, PluginSpec

ThematicExecutor = Callable[[Sequence[CanonicalRecord], Mapping[str, Any]], Mapping[str, Any]]


class ThematicAnalysisAdapterPlugin:
    spec = PluginSpec(
        name="acdt_thematic_analysis",
        version="1.0",
        method_id="thematic_analysis",
        method_version="1.0",
        interpretation_mode="theoretical_interpretive",
        scope="corpus",
        requires=frozenset({"corpus", "text"}),
        produces=frozenset({"themes"}),
        deterministic=False,
    )

    def __init__(self, executor: ThematicExecutor) -> None:
        self.executor = executor

    def process_corpus(
        self,
        records: Sequence[CanonicalRecord],
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context
        output = dict(self.executor(records, config))
        themes = output.get("themes", [])
        if not isinstance(themes, list):
            raise ValueError("thematic-analysis executor must return a list in output['themes']")

        known = {record.source_url for record in records}
        for theme in themes:
            if not isinstance(theme, Mapping):
                raise ValueError("each theme must be a mapping")
            evidence_ids = theme.get("evidence_record_ids", [])
            if not evidence_ids:
                raise ValueError("each thematic interpretation requires evidence_record_ids")
            unknown = {str(item) for item in evidence_ids} - known
            if unknown:
                raise ValueError(f"theme refers to unknown evidence records: {sorted(unknown)}")

        output.setdefault("human_review_status", "provisional")
        output.setdefault(
            "semantic_status",
            "theme_is_interpretive_category_not_laclaudian_discourse_or_ideology_by_default",
        )
        return output
