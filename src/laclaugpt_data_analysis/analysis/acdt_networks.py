"""Source-factual actor-network compatibility plugin for AC/DT workflows."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from ..canonical import CanonicalRecord
from ..plugin_pipeline import PluginContext, PluginSpec


class ActorInteractionNetworkPlugin:
    """Build a directed actor/mention interaction network with evidence drill-down.

    Edges are source-factual communication traces. They are not discourse coalitions,
    ideological formations, equivalence relations or antagonistic frontiers.
    """

    spec = PluginSpec(
        name="acdt_actor_network",
        phase=2, default_enabled=False, experimental=True,
        version="1.0",
        method_id="social_network_analysis",
        method_version="1.0",
        interpretation_mode="measurement",
        scope="corpus",
        requires=frozenset({"corpus", "metadata"}),
        produces=frozenset({"actor_network"}),
        deterministic=True,
    )

    def process_corpus(
        self,
        records: Sequence[CanonicalRecord],
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context
        include_mentions = bool(config.get("include_mentions", True))
        min_edge_count = int(config.get("min_edge_count", 1))
        node_counts: Counter[str] = Counter()
        edge_counts: Counter[tuple[str, str, str]] = Counter()
        evidence: dict[tuple[str, str, str], list[str]] = {}

        for record in records:
            source = record.source.author or record.source_native_ids.get("actor_id") or ""
            if not source:
                continue
            node_counts[source] += 1
            metadata = record.source.raw_metadata
            if include_mentions:
                mentions = metadata.get("mentions", []) or []
                if isinstance(mentions, str):
                    mentions = [mentions]
                for target_raw in mentions:
                    target = str(target_raw).strip().lstrip("@")
                    if not target:
                        continue
                    node_counts[target] += 0
                    edge = (source, target, "mention")
                    edge_counts[edge] += 1
                    evidence.setdefault(edge, []).append(record.source_url)

            interactions = metadata.get("interaction_ids", {}) or {}
            if isinstance(interactions, Mapping):
                for relation in ("reply_to_actor", "repost_actor", "quote_actor"):
                    target = str(interactions.get(relation) or "").strip()
                    if not target:
                        continue
                    node_counts[target] += 0
                    edge = (source, target, relation)
                    edge_counts[edge] += 1
                    evidence.setdefault(edge, []).append(record.source_url)

        return {
            "nodes": [
                {"id": actor, "source_record_count": count}
                for actor, count in sorted(node_counts.items())
            ],
            "edges": [
                {
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "count": count,
                    "evidence_record_ids": evidence[(source, target, relation)],
                }
                for (source, target, relation), count in sorted(edge_counts.items())
                if count >= min_edge_count
            ],
            "semantic_status": "interaction_network_not_discourse_coalition_or_ideology",
        }
