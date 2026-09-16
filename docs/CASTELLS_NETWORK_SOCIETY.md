# Experimental Castells / Network Society analysis

This layer is optional and disabled by default with `LACLAUGPT_CASTELLS_ENABLED=false`.

It operationalizes a limited set of questions inspired by Manuel Castells while keeping measured network properties distinct from theoretical interpretation. Castells supplies concepts such as flows, switching, communication power, space of flows, space of places and hybrid public space. Formal measures come from social network analysis/network science, not from Castells himself.

## Sources and methodological bridge

Core theory: Manuel Castells, *The Rise of the Network Society*; “Materials for an Exploratory Theory of the Network Society”; *Communication Power*; *Networks of Outrage and Hope*. Anttiroiko is useful for clarifying the relation between Castells' network concept and formal network analysis. González-Bailón & Wang (2016) provides an empirical model for testing claims about networked protest using community structure, structural holes/brokerage and diffusion. Karduni & Sauda (2020) is a useful bridge for hybrid digital/physical space.

The implementation therefore follows this rule:

> measured graph property != automatic evidence of network power

For example, betweenness is stored as betweenness. A researcher may later interpret a high-betweenness node as a possible switcher/broker, but the metric itself is not labelled as power.

## Data model

`analysis.castells` provides reusable structures:

- `NetworkNode`
- `NetworkEdge`
- `FlowEvent`
- `BrokerScore`

Edges preserve relation type, observed/inferred status, weight, timestamp, platform, collection ID, source URL and evidence IDs. Existing canonical graph/storage surfaces should be reused rather than creating a second graph database schema.

## Multiplex layers

Separate relation layers can include actor-actor mentions/replies/reposts, actor-institution links, actor-signifier/frame relations, source-domain links, document-location relations and cross-platform references. `multiplex_layers()` groups the same canonical edge set by relation type.

Observed interaction edges and inferred semantic-similarity edges must never be silently mixed. Every edge has an explicit `observed` flag.

## Standard network measures

`build_networkx_graph()` and `graph_measures()` provide reproducible descriptive measures:

- degree, in-degree, out-degree
- betweenness
- PageRank
- clustering
- k-core
- weak components
- density

NetworkX lives in the `analysis` extra and development environment. Larger Roihu experiments may later benchmark igraph, Networkit or RAPIDS cuGraph without changing the canonical output contract.

## Brokerage / switching

`broker_scores()` combines three structural indicators:

- betweenness centrality
- share of ties crossing a supplied community partition
- participation coefficient across communities

This supports empirical questions about bridges between ideological formations, arenas, countries, institutions, platforms or topic communities. It does not claim that these metrics fully operationalize Castells' switching power.

## Temporal flows

`temporal_flows()` materializes time-ordered communication events while retaining source/platform provenance. These can later support cascade depth/width, cross-platform jumps, community transmission and signifier/frame diffusion.

## Space of flows / places

`geographic_flows()` joins graph edges to an explicit node-to-place mapping and aggregates place-to-place flows. Missing locations remain missing. Future geospatial enrichments must distinguish source-provided location, organization location, inferred location and event location.

## Hybrid space

Hybrid-space analysis should combine communication edges, explicitly geocoded events/places, organizations and timelines. The software should make it possible to test whether online communication and occupied/physical space form a hybrid public space rather than assuming that theoretical conclusion.

## Sensitivity and platform limits

`edge_definition_sensitivity()` reports how network size and observed/inferred composition change under alternative edge definitions. Research reports should also document sampling/API limitations, unavailable follower graphs, platform affordances and missingness.

## Downstream visualization contract

Derived outputs can be consumed by Data Visualization as ordinary graph/tabular/geospatial products for broker highlighting, temporal networks, cross-platform graphs, geographic flows and flow/place comparisons. No Castells-specific visualization framework is required.

## Current status

This is an experimental library layer only. It does not change the default AI26 pipeline and should later be registered as one optional Analysis plugin in the generic plugin architecture.
