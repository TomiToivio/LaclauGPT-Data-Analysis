"""Step 7 of 7 — Social Network Analysis (SNA).

Build and measure the network over the statements from step 6: nodes, edges and
conventional network-science metrics.

New in Phase 2. The legacy pipeline has no network layers.

---------------------------------------------------------------------------
Purpose
---------------------------------------------------------------------------

Turn statements into a measurable network:

  nodes   actors (and concepts, when a two-mode view is wanted)
  edges   co-support, co-rejection, or conflict between actors
  metrics degree, density, betweenness, closeness, community structure

Out of scope: saying what the numbers mean. See the boundary note below.

---------------------------------------------------------------------------
Legacy reference
---------------------------------------------------------------------------

None. Semantics follow the implementation verified in issue #307, which matches
leifeld-lab/dna's exporter:

  * a one-mode actor projection is the stacked sum of co-support and
    co-rejection, not an average;
  * there is no minimum-shared-concepts threshold, and the diagonal is omitted;
  * uncoded agreement contributes nothing.

---------------------------------------------------------------------------
Inputs
---------------------------------------------------------------------------

  step_outputs.dna.output.statements   the statements to build the network from
  context.options                      which projection and which metrics

---------------------------------------------------------------------------
Outputs
---------------------------------------------------------------------------

  step_outputs.sna.output =
      Step7SnaOutput {
          nodes:  [SnaNode{node_id, node_type, label}]
          edges:  [SnaEdge{edge_id, source, target, relation_type, weight,
                           communication_mode}]
          metrics: dict
          interpretation_boundary: str
      }

---------------------------------------------------------------------------
Model
---------------------------------------------------------------------------

No LLM. This step is deterministic. Use the verified layer rather than
reimplementing the projections:

  src/laclaugpt_data_analysis/sna/          graph, metrics, communities, exchange
  src/laclaugpt_data_analysis/discourse_network/   DNA projections

NetworkX is the reference layer; igraph/leidenalg remain optional backends.

---------------------------------------------------------------------------
Uncertainty and the interpretation boundary
---------------------------------------------------------------------------

THE RULE FOR THIS STEP: no metric is a theoretical construct.

Betweenness may be evidence relevant to a Castells-informed analysis of
switching and gatekeeping. It is not "network power", and it must not be
relabelled as one. Construct is not measure, position is not power, and network
data carry measurement error.

Compute conventionally; interpret separately, with evidence and argument.

  too few statements to build anything -> empty nodes/edges and ABSTAINED
  a metric undefined for the graph shape (for example eigenvector centrality on
  a disconnected graph) -> omit it rather than reporting a misleading number

Heterogeneous communicators are representable: a node may be a person,
organisation, platform, LLM, bot or algorithmic system, and an edge records
whether the interaction was human-generated, machine-generated or
machine-mediated. Do not assume every actor is a biological human.

---------------------------------------------------------------------------
Provenance
---------------------------------------------------------------------------

Which statements, which projection and which metric definitions produced each
number, so a reported metric can be recomputed. The RDF export carries the SNA
layer alongside the source and discourse layers, with the stage boundaries kept
explicit.

---------------------------------------------------------------------------
"""
from __future__ import annotations

from models.incoming import IncomingRecord
from models.steps import Step7SnaOutput

from steps import StepContext, StepResult, StepStatus


def run(record: IncomingRecord, *, context: StepContext) -> StepResult:
    """Build and measure the network over one record's statements.

    TO HAND-CODE (step 2 of issue #315). The body below is the shape, not the
    method.
    """
    statements = ((record.step_outputs.get("dna") or {}).get("output") or {}).get("statements") or []
    if not statements:
        return StepResult(
            status=StepStatus.ABSTAINED,
            output=Step7SnaOutput(),
            notes=["no statements to build a network from"],
        )

    # ---------------------------------------------------------------- TO CODE
    # Expected shape of the finished body, for readability:
    #
    #   statements = coerce_to_discourse_statements(statements)
    #   edges = dna_actor_projection(statements)          # or conflict=True
    #   nodes, sna_edges = to_sna(edges)
    #   graph = build_graph(nodes, sna_edges)
    #   metrics = graph_metrics(graph)                    # descriptive only
    #   return StepResult(output=Step7SnaOutput(
    #       nodes=nodes, edges=sna_edges, metrics=metrics))
    raise NotImplementedError(
        "step 7 (SNA) is hand-coded by the researcher; see the module docstring"
    )
